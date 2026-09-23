# Протокол JobHunter ↔ Hermes ↔ LLM Gateway

Этот документ описывает два сообщения, из которых состоит вся интеграция workflow
(JobHunter) с координатором (Hermes) и моделью (LLM Gateway → Router → конкретная
модель). Формат специально сделан универсальным — тот же протокол, один в один,
можно использовать для других workflow-проектов (X Publisher, CRM, eBay и т.д.),
меняя только набор задач (task) и их поля input/output.

## 1. LLM_REQUEST (workflow → LLM Gateway)

Workflow (JobHunter или любой другой) никогда не вызывает модель напрямую — только
через `llm_gateway.py`. Запрос:

```
LLM_REQUEST
task  = <имя задачи>
input = { ...специфичные для задачи поля... }
```

В коде это вызов `llm_gateway.request(task, input) -> dict`, либо одна из
task-обёрток (`vacancy_fit`, `cv_match`, `personalize_application` — см.
`scripts/llm_gateway.py`).

Задачи JobHunter:

| task | input | output |
|---|---|---|
| `vacancy_fit` | `{vacancy, candidate_profile}` | `{score: 0-100, reason: str}` |
| `cv_match` | `{vacancy, resume}` | `{matched_skills: [...], missing_skills: [...], notes: str}` |
| `personalize_application` | `{vacancy, resume, cv_match}` | `{cover_letter: str, resume_adjustments: str}` |

Для новых workflow (X Publisher, CRM, eBay) — просто определяете свои task/input/output
в отдельном файле `llm_tasks.md` рядом со своим `llm_gateway.py`, сам Gateway (обвязка
`request()`/`set_backend()`) переиспользуется без изменений.

## 2. Подключение backend'а (Hermes → workflow)

Перед запуском workflow Hermes обязан вызвать:

```python
llm_gateway.set_backend(fn)  # fn(task: str, input: dict) -> dict
```

`fn` — это то место, где Hermes Router выбирает конкретную модель (GPT/Claude/другая)
и превращает `(task, input)` в промпт под эту модель, парсит ответ обратно в dict.
Workflow про это ничего не знает — для него `fn` абсолютно прозрачна.

Если `set_backend` не вызван — `llm_gateway.request()` кидает `LLMBackendNotConfigured`,
и весь workflow (JobHunter) обязан деградировать до чисто кодовой логики, а не падать
(так и сделано: rule-based score в `match_score.py` + шаблонное письмо в
`apply_or_notify.py`).

## 3. JOB_SEARCH_COMPLETED (workflow → Hermes → Telegram)

Когда workflow заканчивает прогон, он возвращает событие с итогами:

```json
{
  "event": "JOB_SEARCH_COMPLETED",
  "checked": 42,
  "matched": 8,
  "great": 3,
  "applied": 1
}
```

В коде — это возврат `run.py::run(...)`; Hermes читает это (например, из stdout
запуска скрипта или из возврата вызова скилла) и решает, что показать пользователю
в Telegram. `telegram_notify.notify_job_search_completed(stats)` — готовая функция
для случаев, когда workflow шлёт сообщение сам (без промежуточного шага через Hermes).

Для других workflow по этому же шаблону: `event` меняется на что-то своё
(`POST_PUBLISHED`, `LEAD_SYNCED`, `LISTING_UPDATED`...), набор полей — свой, но
сама механика (workflow считает → отдаёт структурированный dict → Hermes решает,
как уведомить пользователя) остаётся одинаковой.
