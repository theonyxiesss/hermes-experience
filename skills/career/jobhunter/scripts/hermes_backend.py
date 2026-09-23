"""
hermes_backend.py — конкретная реализация llm_gateway backend для запуска
JobHunter ВНУТРИ Hermes Agent, через `hermes -z` (oneshot-режим CLI).

Зачем этот файл:
PROTOCOL.md / SKILL.md говорят, что Hermes должен один раз вызвать
`llm_gateway.set_backend(fn)` перед запуском workflow, подставив свой
собственный вызов модели. Раньше это оставалось как псевдокод ("your model
call here"). Этот файл — рабочая реализация: `fn` здесь — это subprocess-вызов
`hermes -z "<prompt>"`, который использует ту модель, что уже настроена в
~/.hermes/config.yaml (на момент написания: openrouter /
nvidia/nemotron-3-ultra-550b-a55b:free, с fallback на локальный Ollama
qwen3:14b, если настроен fallback_model). `hermes -z` — существующий
"oneshot" режим CLI Hermes Agent (hermes_cli/oneshot.py): отправляет промпт,
возвращает финальный текстовый блок в stdout и ничего больше (без баннера,
спиннера, session_id) — то есть именно то, что нужно для программного
вызова из скрипта.

Использование (уже подключено автоматически в run.py — см. _auto_configure_backend):
    import llm_gateway
    from hermes_backend import hermes_oneshot_backend
    llm_gateway.set_backend(hermes_oneshot_backend)

Если нужно ЯВНО отключить автоподключение (например, чтобы Hermes сам
подставил другой backend — прямой вызов модели без под-процесса, дешевле по
латентности) — выставьте переменную окружения JOBHUNTER_NO_AUTO_BACKEND=1
перед запуском run.py.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

# Название/путь исполняемого файла hermes. На Windows-инсталляции стоит как
# hermes.exe в venv\Scripts, обычно уже добавлен в PATH инсталлятором —
# используем просто "hermes" и полагаемся на PATH, с одним fallback-поиском.
_HERMES_BIN = shutil.which("hermes") or "hermes"

_TIMEOUT_SECONDS = 120

# ---------------------------------------------------------------------------
# Промпты под каждую task из PROTOCOL.md. Каждый явно требует "ТОЛЬКО JSON,
# без markdown-разметки" — это единственная непредсказуемая часть моста
# (модели иногда всё равно оборачивают ответ в ```json ... ```), поэтому
# ниже есть отдельный устойчивый JSON-экстрактор _extract_json().
# ---------------------------------------------------------------------------

_PROMPTS = {
    "vacancy_fit": (
        "Ты — модуль анализа вакансий внутри workflow JobHunter. "
        "Оцени, насколько вакансия подходит кандидату.\n\n"
        "Вакансия (JSON):\n{vacancy}\n\n"
        "Профиль кандидата:\n{candidate_profile}\n\n"
        "Ответь СТРОГО в виде одного JSON-объекта, без markdown-разметки, "
        "без ```, без пояснений до или после — только сам объект:\n"
        '{{"score": <целое число 0-100>, "reason": "<краткое обоснование, 1-2 предложения>"}}'
    ),
    "cv_match": (
        "Ты — модуль сопоставления резюме и вакансии внутри workflow JobHunter. "
        "Сравни резюме кандидата с требованиями вакансии.\n\n"
        "Вакансия (JSON):\n{vacancy}\n\n"
        "Резюме кандидата:\n{resume}\n\n"
        "Ответь СТРОГО в виде одного JSON-объекта, без markdown-разметки, "
        "без ```, без пояснений до или после — только сам объект:\n"
        '{{"matched_skills": ["..."], "missing_skills": ["..."], "notes": "<1-2 предложения>"}}'
    ),
    "personalize_application": (
        "Ты — модуль персонализации отклика внутри workflow JobHunter. "
        "Напиши короткое сопроводительное письмо под конкретную вакансию.\n\n"
        "Вакансия (JSON):\n{vacancy}\n\n"
        "Резюме кандидата:\n{resume}\n\n"
        "Результат сопоставления навыков (JSON):\n{cv_match}\n\n"
        "Ответь СТРОГО в виде одного JSON-объекта, без markdown-разметки, "
        "без ```, без пояснений до или после — только сам объект:\n"
        '{{"cover_letter": "<сопроводительное письмо, 3-6 предложений>", '
        '"resume_adjustments": "<что стоит подчеркнуть/поправить в резюме под эту вакансию, '
        'или пустая строка>"}}'
    ),
}


class HermesCLIError(RuntimeError):
    pass


def _extract_json(raw: str) -> dict:
    """Достаёт JSON-объект из ответа модели, даже если он обёрнут в ```json ... ```
    или окружён лишним текстом. Бросает ValueError, если валидный объект не найден."""
    text = raw.strip()

    # Снять ```json ... ``` / ``` ... ``` обёртку, если есть.
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    # Прямая попытка.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: взять подстроку от первой "{" до последней "}".
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Не удалось распарсить JSON из ответа hermes -z: {exc}\n"
                f"Сырой ответ:\n{raw[:2000]}"
            ) from exc

    raise ValueError(f"Ответ hermes -z не содержит JSON-объекта:\n{raw[:2000]}")


def hermes_oneshot_backend(task: str, input: dict) -> dict:
    """Реализация сигнатуры llm_gateway.set_backend: fn(task: str, input: dict) -> dict.

    Формирует промпт под конкретную task (vacancy_fit / cv_match /
    personalize_application), вызывает `hermes -z "<prompt>"` как под-процесс
    и парсит результат обратно в dict.
    """
    prompt_template = _PROMPTS.get(task)
    if prompt_template is None:
        raise ValueError(f"hermes_backend: неизвестная task={task!r} (нет промпта)")

    format_args = {
        k: (json.dumps(v, ensure_ascii=False, indent=2) if isinstance(v, (dict, list)) else v)
        for k, v in input.items()
    }
    prompt = prompt_template.format(**format_args)

    try:
        result = subprocess.run(
            [_HERMES_BIN, "-z", prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise HermesCLIError(
            "Команда 'hermes' не найдена в PATH. Проверьте, что Hermes Agent "
            "установлен и venv/Scripts (или bin/) добавлен в PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HermesCLIError(
            f"hermes -z не ответил за {_TIMEOUT_SECONDS}s (task={task})"
        ) from exc

    if result.returncode != 0:
        raise HermesCLIError(
            f"hermes -z завершился с кодом {result.returncode} (task={task}).\n"
            f"stderr:\n{result.stderr.strip()[:2000]}"
        )

    return _extract_json(result.stdout)


if __name__ == "__main__":
    # Ручная диагностика: python hermes_backend.py
    # Прогоняет один тестовый вызов task=vacancy_fit на заведомо фиктивных данных
    # (не трогает реальные вакансии/резюме/Telegram) и печатает результат.
    dummy_vacancy = {
        "id": "test-0",
        "title": "Python Backend Developer",
        "company": "Test Co",
        "description": "Django, PostgreSQL, remote, 250000 RUR",
    }
    dummy_profile = "Желаемые роли: Python developer. Стек: python, django, postgresql."
    print("Вызываю hermes -z для task=vacancy_fit (диагностика, без реальных данных)...")
    out = hermes_oneshot_backend("vacancy_fit", {"vacancy": dummy_vacancy, "candidate_profile": dummy_profile})
    print(json.dumps(out, ensure_ascii=False, indent=2))
