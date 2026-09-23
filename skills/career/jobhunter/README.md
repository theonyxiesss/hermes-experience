# JobHunter

Workflow-скилл для Hermes Agent: ищет вакансии, дёшево фильтрует кодом, для
неоднозначных случаев зовёт LLM Gateway (анализ вакансии + CV matching),
готовит персонализированный отклик и присылает в Telegram.

Подробная схема — в [`ARCHITECTURE.md`](./ARCHITECTURE.md).
Контракт LLM_REQUEST / JOB_SEARCH_COMPLETED (переиспользуемый для других
проектов) — в [`PROTOCOL.md`](./PROTOCOL.md).
База источников вакансий — в [`references/job_sources.json`](./references/job_sources.json).

## Установка в Hermes Agent

1. Скопируйте эту папку в `~/.hermes/skills/career/jobhunter/` (структура папок
   уже правильная — `SKILL.md` должен лежать прямо внутри). **Уже сделано** —
   установлено в `C:\Users\Admin\AppData\Local\hermes\skills\career\jobhunter\`.
2. `pip install -r requirements.txt` (или дайте это сделать самому Hermes Agent —
   он умеет ставить зависимости скиллов).
3. Задайте переменные окружения (Hermes спросит их сам при первом использовании
   скилла благодаря `required_environment_variables` в `SKILL.md`, либо задайте
   вручную):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `HH_ACCESS_TOKEN` (необязательно, только для автоподачи через hh.ru)
   - `HH_RESUME_ID` (необязательно, вместе с HH_ACCESS_TOKEN)
4. Проверьте доставку в Telegram: `python scripts/telegram_notify.py --test`
5. Заполните `references/criteria.json` (структурированные правила отбора — код
   читает именно его) и `assets/resume_template.md` — без них workflow работает
   по дефолтным/пустым значениям.
6. LLM Gateway подключается АВТОМАТИЧЕСКИ через `scripts/hermes_backend.py`
   (мост к `hermes -z`, использует модель из `~/.hermes/config.yaml` —
   сейчас это openrouter / nvidia/nemotron-3-ultra-550b-a55b:free) — ручных
   действий на стороне Hermes не требуется. Проверить, что мост реально
   работает: `python scripts/hermes_backend.py` (тестовый вызов на фиктивных
   данных, не трогает реальные вакансии/резюме). Подробности и как отключить
   автоподключение — в `SKILL.md`, шаг 0.
7. Спросите у Hermes Agent: «запусти JobHunter, ищи вакансии каждые 3 часа» —
   дальше он сам вызывает `scripts/run.py::run()` по расписанию.

## Пайплайн, а не ИИ на каждом шаге

Большая часть workflow — обычный код (поиск, дедупликация, хранение, rule-based
скоринг). LLM Gateway вызывается только для вакансий, уже прошедших дешёвый
код-фильтр, и только для трёх задач, где реально нужно понимание: анализ
вакансии, сопоставление CV, персонализация письма. Подробности — в
`ARCHITECTURE.md`.

## Что уже готово / что осталось (статус на 2026-08-20)

- [x] Архитектура по вашей схеме (Hermes Coordinator → JobHunter Workflow → LLM Gateway → Application Workflow → Hermes → Telegram)
- [x] База источников вакансий по категориям
- [x] Структура скилла под Hermes Agent (open Agent Skills формат)
- [x] Рабочий код поиска (hh.ru, RemoteOK, Remotive, We Work Remotely)
- [x] Детерминированный Score/Filter по правилам (`criteria.json`), без ИИ
- [x] LLM Gateway (model-agnostic, протокол LLM_REQUEST) с task-обёртками vacancy_fit / cv_match / personalize_application
- [x] Database с статусами и историей (`state.py`)
- [x] Application Workflow (персонализация + опц. автоподача hh.ru)
- [x] Оркестратор `run.py` (JobHunter Workflow целиком) + событие JOB_SEARCH_COMPLETED
- [x] Установлено в `~/.hermes/skills/career/jobhunter/` — Hermes обнаруживает скилл автоматически (сканирует `SKILL.md`)
- [x] LLM Gateway подключён к реальному backend'у Hermes (`hermes_backend.py` → `hermes -z`) — авто-подключается в `run.py`, проверено вызовом `python scripts/hermes_backend.py`
- [ ] `references/criteria.json` — ваши реальные критерии (заготовка/пример есть, нужно подтвердить или заменить)
- [ ] `assets/resume_template.md` — ваше резюме (заготовка пустая, нужен реальный текст)
- [ ] `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — нужно создать бота через @BotFather и задать переменные окружения
- [ ] По желанию: OAuth для автоподачи через hh.ru (`HH_ACCESS_TOKEN` + `HH_RESUME_ID`)

## Структура

```
job-hunter/
├── SKILL.md                     # инструкция для Hermes Agent (открытый Agent Skills формат)
├── ARCHITECTURE.md               # схема, диаграмма, обоснования
├── PROTOCOL.md                   # контракт LLM_REQUEST / JOB_SEARCH_COMPLETED
├── README.md                     # этот файл
├── requirements.txt
├── scripts/
│   ├── run.py                    # JobHunter Workflow — точка входа, вызывается Hermes'ом
│   ├── hermes_backend.py         # мост llm_gateway → `hermes -z` (реальный LLM backend)
│   ├── search_jobs.py             # Job Sources: 81 площадка, 16 полных адаптеров (API+RSS+key-based)
│   ├── match_score.py            # Score/Filter: детерминированный rule-based скоринг (без ИИ)
│   ├── llm_gateway.py            # LLM Gateway: единая точка входа для LLM-задач, model-agnostic
│   ├── apply_or_notify.py        # Application Workflow: персонализация письма + опц. автоподача hh.ru
│   ├── telegram_notify.py        # доставка в Telegram + JOB_SEARCH_COMPLETED (код, без ИИ)
│   └── state.py                  # Filters + Database: дедуп, статусы, история (SQLite, без ИИ)
├── references/
│   ├── job_sources.json          # база сайтов по категориям
│   ├── criteria.json             # структурированные критерии отбора (заполнить) — читает код
│   └── criteria_prompt.md        # человекочитаемая памятка/пояснение к criteria.json
├── assets/
│   └── resume_template.md        # ваше резюме (заполнить)
└── examples/
    └── sample_run.md             # пример одного прогона от начала до конца
```
