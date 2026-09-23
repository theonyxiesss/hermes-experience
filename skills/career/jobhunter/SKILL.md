---
name: jobhunter
description: JobHunter workflow — ищет вакансии, дёшево фильтрует кодом, для неоднозначных случаев зовёт LLM Gateway (анализ вакансии + CV matching), готовит персонализированный отклик и присылает в Telegram (и опционально подаёт заявку через hh.ru API)
version: 0.3.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [job-search, telegram, hh.ru, career, workflow, llm-gateway]
    category: career
    config:
      - key: search.interval_hours
        description: Как часто запускать JobHunter Workflow
        default: "3"
      - key: match.score_threshold
        description: Минимальный итоговый score (0-100) для уведомления/отклика
        default: "70"
required_environment_variables:
  - name: TELEGRAM_BOT_TOKEN
    prompt: Токен вашего Telegram-бота от @BotFather
  - name: TELEGRAM_CHAT_ID
    prompt: Chat ID, куда бот будет присылать вакансии (ваш личный чат с ботом)
  - name: HH_ACCESS_TOKEN
    prompt: "(необязательно) OAuth-токен hh.ru для автоподачи откликов — оставьте пустым, если не нужен автопилот"
  - name: HH_RESUME_ID
    prompt: "(необязательно) id вашего резюме на hh.ru — нужен только вместе с HH_ACCESS_TOKEN"
---

# JobHunter — workflow поиска и подачи заявок на вакансии

Архитектура (полная схема и обоснования — в `ARCHITECTURE.md`, контракт
LLM-задач — в `PROTOCOL.md`):

```
Hermes Coordinator → «Запусти JobHunter» → JobHunter Workflow (scripts/run.py)
    → Job Sources + Filters + Database (код, без ИИ)
    → Score/Filter (код, match_score.py) — дешёвый пре-фильтр
    → LLM Task → LLM Gateway → Hermes Router → модель → vacancy_fit + cv_match
    → Application Workflow (apply_or_notify.py) → Telegram
    → JOB_SEARCH_COMPLETED → Hermes → Telegram-сводка
```

## When to Use

Используй этот скилл, когда нужно периодически (по расписанию, см.
`search.interval_hours`) запускать JobHunter Workflow, либо по прямому запросу
пользователя: «запусти JobHunter», «поищи вакансии сейчас», «проверь новые
вакансии», «обнови критерии поиска».

## Procedure

**Шаг 0 (обычно ничего делать не нужно — подключается автоматически):**
`run.py` при вызове `run()` сам подключает LLM Gateway через
`hermes_backend.py` — мост к `hermes -z` (oneshot-режим CLI Hermes Agent),
который использует ту модель, что уже настроена в `~/.hermes/config.yaml`.
Ручной вызов `llm_gateway.set_backend(...)` нужен только если вы хотите
подставить другой backend (например, прямой вызов модели без под-процесса —
дешевле по латентности) — тогда вызовите его САМИ до `run()` и выставите
`JOBHUNTER_NO_AUTO_BACKEND=1`, чтобы авто-подключение не перезаписало его:

```python
import llm_gateway
llm_gateway.set_backend(lambda task, input: <свой вызов модели по протоколу PROTOCOL.md>)
```

Если backend в итоге не настроен (ни авто, ни вручную — например, команда
`hermes` недоступна в PATH) — workflow всё равно отработает: `run.py`
проверяет `llm_gateway.is_configured()` и при отсутствии backend'а использует
только код-фильтр (`match_score.py`) и шаблонные письма
(`apply_or_notify.py`), без LLM-уточнения.

**Шаг 1:** вызвать `scripts/run.py::run(text, area, hours)` (или как отдельный
процесс: `python run.py --text "..." --hours 6`). Это и есть весь workflow —
дальше он сам:

1. **Job Sources**: `search_jobs.py` — забирает вакансии из источников с
   `enabled: true` в `references/job_sources.json` (16 полных адаптеров:
   API + RSS + key-based, остальные — заглушки под scrape).
2. **Filters + Database**: `state.py` — дедуп по id, сохраняет вакансию и
   статус, ведёт историю переходов. Всё это — код, без ИИ.
3. **Score/Filter**: `match_score.py::score_vacancy()` — детерминированная
   оценка по `references/criteria.json` (роли, стек, зарплата, локация,
   красные флаги, чёрный список). Вакансии с явным red_flag или score ниже
   `match_score.LOW_BAR_FOR_LLM` отсеиваются здесь же, без обращения к модели.
4. **LLM Task** (только для вакансий, прошедших шаг 3, и только если Gateway
   подключен): `llm_gateway.vacancy_fit()` — "подходит ли вакансия?", и
   `llm_gateway.cv_match()` — "какие навыки совпадают/отсутствуют?". Итоговый
   score — среднее кодового и LLM-score.
5. Если итоговый score >= `match.score_threshold`:
   a. **Application Workflow**: `apply_or_notify.py::process_vacancy()` —
      генерирует сопроводительное (`llm_gateway.personalize_application()`,
      либо шаблон без ИИ) и, если источник hh.ru и заданы `HH_ACCESS_TOKEN`
      + `HH_RESUME_ID`, опционально подаёт отклик через API.
   b. `telegram_notify.notify_vacancy()` — вакансия + score + причина +
      сопроводительное + статус (отправлено само / нужно подтвердить вручную).
6. Если score ниже порога — вакансия помечается `rejected`, не показывается.
7. В конце `run()` возвращает `{"checked", "matched", "great", "applied"}` —
   это и есть payload события **JOB_SEARCH_COMPLETED** (см. `PROTOCOL.md`).
   Передать это пользователю в Telegram может либо сам Hermes (получив
   возврат вызова), либо `telegram_notify.notify_job_search_completed(stats)`,
   если скрипт запущен отдельным процессом.

## Pitfalls

- Не включать источники с `access: scrape` в `job_sources.json` без явного
  согласия пользователя — это может нарушать условия использования площадки.
- Не пытаться автоматизировать LinkedIn/Indeed — публичного API для отклика
  нет, риск блокировки аккаунта пользователя.
- Не звать LLM Gateway для вакансий, не прошедших `match_score.py` — это
  единственная причина, по которой пайплайн остаётся дешёвым при большом
  потоке вакансий. Если этот порядок нарушить (сначала LLM, потом фильтр),
  расходы на модель вырастут на порядок без выигрыша в качестве.
- Порог `match.score_threshold` калибровать вместе с пользователем в первые
  дни — слишком низкий спамит нерелевантным, слишком высокий пропускает
  хорошие варианты.
- `hermes_backend.py` вызывает `hermes -z` под-процессом на каждую LLM-задачу
  (до 3 вызовов на вакансию, прошедшую пре-фильтр) — при большом потоке
  вакансий это добавляет заметную латентность и расход по модели у
  провайдера (openrouter). Это ожидаемо и совпадает с дизайном пайплайна
  (LLM зовётся только после дешёвого код-фильтра), но стоит иметь в виду при
  калибровке `search.interval_hours`.

## Verification

- После первого запуска показать пользователю `JOB_SEARCH_COMPLETED` целиком
  (checked/matched/great/applied), чтобы можно было скорректировать критерии
  или порог.
- Проверить, что сообщения реально доходят до Telegram: `python
  scripts/telegram_notify.py --test`.
- Проверить, что backend реально подключился: `python scripts/hermes_backend.py`
  — прогоняет один тестовый вызов task=vacancy_fit на фиктивных данных через
  `hermes -z` и печатает результат. Если падает — `llm_gateway.is_configured()`
  всё равно вернёт False внутри `run()`, и workflow тихо задеградирует до
  чисто кодового режима (не ошибка, но пользователь должен знать, что сейчас
  работает именно так).
