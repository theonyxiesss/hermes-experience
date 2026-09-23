"""
LLM Gateway — единая точка входа для любых LLM-задач JobHunter.

JobHunter не знает и не должен знать, какая модель стоит за Gateway — GPT, Claude,
локальная модель — маршрутизацию делает Hermes Router. JobHunter просто отправляет
запрос по протоколу:

    LLM_REQUEST
    task  = "vacancy_fit" | "cv_match" | "personalize_application"
    input = { ...специфичные для задачи поля... }

и получает обратно структурированный результат. Полный контракт задач и форматов —
в ../PROTOCOL.md. Тот же протокол и тот же файл (без изменений) можно переиспользовать
в других workflow-проектах (X Publisher, CRM, eBay и т.д.) — просто с другим набором
task-обёрток снизу.

Как это подключается внутри Hermes Agent:
Hermes Agent, выполняя SKILL.md этого скилла, ДОЛЖЕН перед запуском workflow вызвать
llm_gateway.set_backend(fn), подставив свой собственный вызов модели. Это единственная
точка интеграции с моделью во всём проекте — весь остальной код (search_jobs.py,
match_score.py, state.py, application_workflow.py, run.py) от конкретной модели не
зависит и работать с ней напрямую не умеет.

Если backend не подключен (например, тестовый прогон вне Hermes) — request() кидает
LLMBackendNotConfigured. Вызывающий код (run.py) обязан уметь работать без LLM,
используя только rule-based score из match_score.py — то есть отсутствие LLM не
роняет пайплайн, просто снижает точность отбора до чисто механической.
"""

from typing import Callable, Optional

_backend: Optional[Callable[[str, dict], dict]] = None


class LLMBackendNotConfigured(RuntimeError):
    pass


def set_backend(fn: Callable[[str, dict], dict]) -> None:
    """
    Подключить реальный backend. fn(task: str, input: dict) -> dict.
    Вызывается один раз Hermes Agent'ом (или тестовым раннером) перед стартом workflow.
    """
    global _backend
    _backend = fn


def is_configured() -> bool:
    return _backend is not None


def request(task: str, input: dict) -> dict:
    """Низкоуровневый вызов по протоколу LLM_REQUEST. Обычно не нужен напрямую —
    используйте task-обёртки ниже (vacancy_fit / cv_match / personalize_application)."""
    if _backend is None:
        raise LLMBackendNotConfigured(
            f"LLM Gateway backend не подключен (task={task}). "
            "Hermes должен вызвать llm_gateway.set_backend(...) перед запуском JobHunter "
            "(см. SKILL.md -> Procedure, шаг 0)."
        )
    return _backend(task, input)


# ---------------------------------------------------------------------------
# Task-обёртки: формируют input по контракту задачи и парсят output в удобный dict.
# Именно эти три задачи — единственное место во всём JobHunter, где нужно
# "понимание", а не подсчёт. Всё остальное — код.
# ---------------------------------------------------------------------------

def vacancy_fit(vacancy: dict, candidate_profile: str) -> dict:
    """
    task=vacancy_fit — "Подходит ли эта вакансия пользователю?"
    Возвращает {"score": 0-100, "reason": "..."}
    """
    result = request("vacancy_fit", {"vacancy": vacancy, "candidate_profile": candidate_profile})
    return {"score": int(result.get("score", 0)), "reason": result.get("reason", "")}


def cv_match(vacancy: dict, resume_text: str) -> dict:
    """
    task=cv_match — "Какие навыки совпадают? Что отсутствует?"
    Возвращает {"matched_skills": [...], "missing_skills": [...], "notes": "..."}
    """
    result = request("cv_match", {"vacancy": vacancy, "resume": resume_text})
    return {
        "matched_skills": result.get("matched_skills", []),
        "missing_skills": result.get("missing_skills", []),
        "notes": result.get("notes", ""),
    }


def personalize_application(vacancy: dict, resume_text: str, cv_match_result: dict) -> dict:
    """
    task=personalize_application — адаптирует сопроводительное (и, по желанию, акценты
    резюме) под конкретную вакансию, с учётом результата cv_match.
    Возвращает {"cover_letter": "...", "resume_adjustments": "..."}
    """
    result = request(
        "personalize_application",
        {"vacancy": vacancy, "resume": resume_text, "cv_match": cv_match_result},
    )
    return {
        "cover_letter": result.get("cover_letter", ""),
        "resume_adjustments": result.get("resume_adjustments", ""),
    }
