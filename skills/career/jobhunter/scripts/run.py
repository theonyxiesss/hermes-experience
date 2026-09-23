"""
run.py — точка входа "JobHunter Workflow" (сама схема из вашей архитектуры).

    Hermes Coordinator
          │  «Запусти JobHunter»
          ↓
    JobHunter Workflow (этот файл)
          │
    Job Sources → Filters/дедуп → Database   (весь этот блок — код, без ИИ)
          │
    Score/Filter (код, match_score.py)  — дешёвый пре-фильтр
          │
    LLM Task → LLM Gateway → Hermes Router → модель → анализ вакансии + CV matching
          │        (только для вакансий, прошедших пре-фильтр)
          ↓
    Application Workflow (apply_or_notify.py) — сопроводительное + опц. автоподача
          ↓
    Telegram-уведомление
          ↓
    JOB_SEARCH_COMPLETED  →  наверх, в Hermes  →  Telegram-сводка

Как Hermes подключает модель:
    Backend подключается АВТОМАТИЧЕСКИ (см. _auto_configure_backend ниже) через
    hermes_backend.py — мост к `hermes -z` (oneshot-режим CLI Hermes Agent),
    использует ту модель, что настроена в ~/.hermes/config.yaml. Hermes'у не
    нужно ничего вызывать вручную перед run() — если backend ещё не
    подключен явно (например, кастомным fn), run.py подключит его сам при
    первом вызове run().
    Чтобы отключить автоподключение (например, чтобы подставить свой fn):
        set JOBHUNTER_NO_AUTO_BACKEND=1   (Windows)
        export JOBHUNTER_NO_AUTO_BACKEND=1  (macOS/Linux)
    Если backend всё равно не настроен (ни авто, ни вручную) — workflow всё
    равно отработает (см. match_score.py + apply_or_notify.py, у них есть
    fallback без ИИ), просто без LLM-уточнения и без персонализированных
    писем, только на правилах из criteria.json.

Запуск вручную (для теста, без Hermes):
    python run.py --text "python developer"
"""

import argparse
import json
import os
from pathlib import Path

import llm_gateway
import match_score
import search_jobs
import state
import telegram_notify
from apply_or_notify import process_vacancy

CRITERIA_FILE = Path(__file__).resolve().parent.parent / "references" / "criteria.json"
RESUME_FILE = Path(__file__).resolve().parent.parent / "assets" / "resume_template.md"

THRESHOLD_NOTIFY = 70  # ниже — не считается "подходит"
THRESHOLD_GREAT = 90  # выше — считается "отлично подходит"


def _auto_configure_backend() -> None:
    """Подключает hermes_backend.hermes_oneshot_backend, если backend ещё не
    настроен и автоподключение не отключено явно через переменную окружения.
    Тихо игнорирует ошибки импорта/настройки — run() в этом случае просто
    останется без LLM (задеградирует до чисто кодового режима), как и раньше."""
    if llm_gateway.is_configured():
        return
    if os.environ.get("JOBHUNTER_NO_AUTO_BACKEND"):
        return
    try:
        from hermes_backend import hermes_oneshot_backend

        llm_gateway.set_backend(hermes_oneshot_backend)
    except Exception:
        pass  # нет hermes в PATH / не внутри Hermes окружения — работаем без LLM


def build_candidate_profile() -> str:
    """Короткое текстовое описание кандидата для LLM-задачи vacancy_fit — собирается
    из criteria.json + резюме, отдельно заполнять не нужно."""
    parts = []
    if CRITERIA_FILE.exists():
        c = json.loads(CRITERIA_FILE.read_text(encoding="utf-8"))
        parts.append(f"Желаемые роли: {', '.join(c.get('roles_include', [])) or '—'}")
        parts.append(f"Ключевой стек: {', '.join(c.get('keywords_include', [])) or '—'}")
        parts.append(f"Минимальная зарплата: {c.get('salary_min', '—')} {c.get('currency', '')}")
        parts.append(f"Локация: {', '.join(c.get('locations', [])) or '—'} (удалёнка: {c.get('remote_ok', True)})")
    if RESUME_FILE.exists():
        parts.append("Резюме:\n" + RESUME_FILE.read_text(encoding="utf-8"))
    return "\n".join(parts) if parts else "(критерии и резюме ещё не заполнены)"


def run(text: str) -> dict:
    _auto_configure_backend()

    db = state.State()
    candidate_profile = build_candidate_profile()
    resume_text = RESUME_FILE.read_text(encoding="utf-8") if RESUME_FILE.exists() else ""
    vacancies = search_jobs.search_all(text)

    checked = matched = great = applied = 0

    for vacancy in vacancies:
        checked += 1
        if db.seen(vacancy["id"]):
            continue  # Filters: дедуп
        db.upsert_vacancy(vacancy, status="new")

        # --- Score/Filter: дешёвый код-фильтр, ДО любых обращений к ИИ ---
        rule = match_score.score_vacancy(vacancy)
        if rule["red_flag"] or rule["score"] < match_score.LOW_BAR_FOR_LLM:
            db.set_status(vacancy["id"], "rejected_by_rules", score=rule["score"], note=rule["reason"])
            continue

        final_score, reason, cv_match_result = rule["score"], rule["reason"], None

        # --- LLM Task: только для вакансий, прошедших пре-фильтр ---
        if llm_gateway.is_configured():
            try:
                fit = llm_gateway.vacancy_fit(vacancy, candidate_profile)
                cv_match_result = llm_gateway.cv_match(vacancy, resume_text)
                final_score = round((rule["score"] + fit["score"]) / 2)
                reason = f"код: {rule['reason']} | LLM: {fit['reason']}"
            except llm_gateway.LLMBackendNotConfigured:
                pass  # не должно случиться раз is_configured()==True, но не падаем

        db.set_status(vacancy["id"], "scored", score=final_score, note=reason)

        if final_score < THRESHOLD_NOTIFY:
            db.set_status(vacancy["id"], "rejected", score=final_score, note=reason)
            continue

        matched += 1
        if final_score >= THRESHOLD_GREAT:
            great += 1

        # --- Application Workflow ---
        result = process_vacancy(vacancy, cv_match_result=cv_match_result)
        if result["applied"]:
            applied += 1

        telegram_notify.notify_vacancy(
            vacancy, final_score, reason, result["cover_letter"], result["applied"], result["apply_detail"]
        )
        db.set_status(
            vacancy["id"], "applied" if result["applied"] else "notified", score=final_score, note=result["apply_detail"]
        )

    db.close()
    return {"checked": checked, "matched": matched, "great": great, "applied": applied}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True, help="Ключевые слова поиска (роль/стек)")
    parser.add_argument("--notify-summary", action="store_true", help="Прислать JOB_SEARCH_COMPLETED в Telegram")
    args = parser.parse_args()

    stats = run(args.text)
    print(json.dumps(stats, ensure_ascii=False))  # JOB_SEARCH_COMPLETED payload — читает Hermes со stdout

    if args.notify_summary:
        telegram_notify.notify_job_search_completed(stats)
