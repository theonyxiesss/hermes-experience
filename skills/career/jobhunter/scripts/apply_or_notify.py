"""
Application Workflow — компонент "Отправить заявку" из архитектуры JobHunter.

Собирает воедино результат Score/Filter (код) и CV Matching (LLM Gateway), готовит
персонализированное сопроводительное письмо (через llm_gateway.personalize_application,
с шаблонным fallback без ИИ, если Gateway не подключен), и, если это технически
возможно (сейчас — только hh.ru + OAuth), подаёт отклик через API источника.

Файл называется apply_or_notify.py по историческим причинам (первая версия проекта) —
по сути это и есть модуль application_workflow.
"""

import os
from pathlib import Path
from typing import Optional

import requests

import llm_gateway

RESUME_FILE = Path(__file__).resolve().parent.parent / "assets" / "resume_template.md"


def load_resume() -> str:
    if not RESUME_FILE.exists():
        return "(резюме ещё не составлено)"
    return RESUME_FILE.read_text(encoding="utf-8")


def _template_cover_letter(vacancy: dict) -> str:
    """Fallback без ИИ — используется, если LLM Gateway не подключен."""
    return (
        f"Здравствуйте! Меня заинтересовала вакансия «{vacancy.get('title', '')}» "
        f"в {vacancy.get('company', '')}. Резюме приложено, буду рад обсудить детали."
    )


def build_cover_letter(vacancy: dict, cv_match_result: Optional[dict] = None) -> dict:
    """
    Возвращает {"cover_letter": str, "source": "llm" | "template"}.
    Если llm_gateway подключен — task=personalize_application (учитывает cv_match).
    Иначе — простой шаблон, пайплайн не падает и не блокируется на отсутствии ИИ.
    """
    resume = load_resume()
    if llm_gateway.is_configured():
        result = llm_gateway.personalize_application(
            vacancy, resume, cv_match_result or {"matched_skills": [], "missing_skills": [], "notes": ""}
        )
        if result.get("cover_letter"):
            return {"cover_letter": result["cover_letter"], "source": "llm"}
    return {"cover_letter": _template_cover_letter(vacancy), "source": "template"}


def apply_via_hh(vacancy_id_raw: str, cover_letter: str, resume_id: str) -> dict:
    """
    Подать отклик через hh.ru API. Требует:
      - HH_ACCESS_TOKEN в переменных окружения (OAuth-токен соискателя)
      - resume_id — id вашего резюме на hh.ru (найти можно через GET /resumes/mine)
    vacancy_id_raw — чистый id вакансии на hh.ru (без префикса "hh:").
    Возвращает {"applied": bool, "detail": str}.
    """
    token = os.environ.get("HH_ACCESS_TOKEN")
    if not token:
        return {"applied": False, "detail": "HH_ACCESS_TOKEN не задан — автоподача выключена"}

    resp = requests.post(
        "https://api.hh.ru/negotiations",
        headers={"Authorization": f"Bearer {token}"},
        data={"vacancy_id": vacancy_id_raw, "resume_id": resume_id, "message": cover_letter},
        timeout=20,
    )
    if resp.status_code in (200, 201):
        return {"applied": True, "detail": "Отклик отправлен через hh.ru API"}
    return {"applied": False, "detail": f"hh.ru API вернул {resp.status_code}: {resp.text[:200]}"}


def process_vacancy(
    vacancy: dict,
    cv_match_result: Optional[dict] = None,
    hh_resume_id: Optional[str] = None,
) -> dict:
    """
    Главная точка входа Application Workflow. Вызывается из run.py для каждой
    вакансии, прошедшей Score/Filter (+ опционально LLM vacancy_fit).

    Возвращает событие для передачи дальше в notify/DONE:
    {
        "vacancy": {...},
        "cover_letter": "...",
        "cover_letter_source": "llm" | "template",
        "applied": bool,
        "apply_detail": "...",
    }
    """
    letter = build_cover_letter(vacancy, cv_match_result)

    applied = {"applied": False, "detail": "автоподача не настроена для этого источника"}
    if vacancy.get("source") == "hh.ru" and hh_resume_id:
        raw_id = vacancy["id"].split(":", 1)[1]
        applied = apply_via_hh(raw_id, letter["cover_letter"], hh_resume_id)

    return {
        "vacancy": vacancy,
        "cover_letter": letter["cover_letter"],
        "cover_letter_source": letter["source"],
        "applied": applied["applied"],
        "apply_detail": applied["detail"],
    }
