---
name: jobhunter
description: JobHunter workflow — searches for vacancies, filters them cheaply in code, calls the LLM Gateway on ambiguous cases (vacancy analysis + CV matching), drafts a personalized application and sends it to Telegram (optionally submits an application via the hh.ru API).
version: 0.3.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [job-search, telegram, hh.ru, career, workflow, llm-gateway]
    category: career
    config:
      - key: search.interval_hours
        description: How often to run the JobHunter workflow
        default: "3"
      - key: match.score_threshold
        description: Minimum overall score (0-100) required to notify or apply
        default: "70"
required_environment_variables:
  - name: TELEGRAM_BOT_TOKEN
    prompt: Your Telegram bot token from @BotFather
  - name: TELEGRAM_CHAT_ID
    prompt: Chat ID where the bot will send vacancies (your private chat with the bot)
  - name: HH_ACCESS_TOKEN
    prompt: "(optional) hh.ru OAuth token for auto-applying — leave empty if you don't need autopilot"
  - name: HH_RESUME_ID
    prompt: "(optional) your hh.ru resume id — required only together with HH_ACCESS_TOKEN"
---

# JobHunter — vacancy search and application workflow

Architecture (full diagram and rationale in `ARCHITECTURE.md`, LLM task
contract in `PROTOCOL.md`):

```
Hermes Coordinator → "Run JobHunter" → JobHunter Workflow (scripts/run.py)
    → Job Sources + Filters + Database (code, no AI)
    → Score/Filter (code, match_score.py) — cheap pre-filter
    → LLM Task → LLM Gateway → Hermes Router → model → vacancy_fit + cv_match
    → Application Workflow (apply_or_notify.py) → Telegram
    → JOB_SEARCH_COMPLETED → Hermes → Telegram summary
```

## When to Use

Use this skill when JobHunter needs to run on a schedule (see
`search.interval_hours`) or on direct user request: "run JobHunter",
"search for vacancies now", "check new vacancies", "update search
criteria".

## Procedure

**Step 0 (usually nothing to do — auto-wired):**
When `run()` is called, `run.py` auto-wires the LLM Gateway through
`hermes_backend.py` — a bridge to `hermes -z` (Hermes Agent CLI oneshot
mode) which uses the model already configured in `~/.hermes/config.yaml`.
A manual `llm_gateway.set_backend(...)` call is only needed if you want
to inject a different backend (e.g. a direct model call without a
subprocess — lower latency). In that case call it YOURSELF before `run()`
and set `JOBHUNTER_NO_AUTO_BACKEND=1` so the auto-wiring does not
overwrite it:

```python
import llm_gateway
llm_gateway.set_backend(lambda task, input: <your model call following PROTOCOL.md>)
```

If no backend is configured in the end (neither auto nor manual — e.g.
the `hermes` command is not in PATH), the workflow still runs: `run.py`
checks `llm_gateway.is_configured()` and, when the backend is missing,
falls back to code-only filtering (`match_score.py`) and template
messages (`apply_or_notify.py`), without LLM refinement.

**Step 1:** call `scripts/run.py::run(text, area, hours)` (or run it as a
standalone process: `python run.py --text "..." --hours 6`). That's the
entire workflow — from here it runs itself:

1. **Job Sources**: `search_jobs.py` — fetches vacancies from sources
   with `enabled: true` in `references/job_sources.json` (16 full
   adapters: API + RSS + key-based, the rest are scrape stubs).
2. **Filters + Database**: `state.py` — deduplicates by id, stores the
   vacancy and its status, tracks the transition history. All code, no AI.
3. **Score/Filter**: `match_score.py::score_vacancy()` — deterministic
   scoring against `references/criteria.json` (roles, stack, salary,
   location, red flags, blacklist). Vacancies with an explicit red_flag
   or a score below `match_score.LOW_BAR_FOR_LLM` are dropped here,
   without calling the model.
4. **LLM Task** (only for vacancies that passed step 3, and only if the
   Gateway is wired): `llm_gateway.vacancy_fit()` — "is this vacancy a
   fit?", and `llm_gateway.cv_match()` — "which skills match / are
   missing?". The final score is the average of the code and LLM scores.
5. If the final score is >= `match.score_threshold`:
   a. **Application Workflow**: `apply_or_notify.py::process_vacancy()` —
      generates a cover letter (`llm_gateway.personalize_application()`,
      or a template without AI) and, if the source is hh.ru and
      `HH_ACCESS_TOKEN` + `HH_RESUME_ID` are set, optionally submits an
      application through the API.
   b. `telegram_notify.notify_vacancy()` — vacancy + score + reason +
      cover letter + status (auto-sent / needs manual confirmation).
6. If the score is below the threshold, the vacancy is marked
   `rejected` and not shown.
7. At the end `run()` returns `{"checked", "matched", "great",
   "applied"}` — the payload of the **JOB_SEARCH_COMPLETED** event (see
   `PROTOCOL.md`). Either Hermes forwards it to Telegram (by capturing
   the return value) or, if the script runs as a standalone process,
   `telegram_notify.notify_job_search_completed(stats)` does it.

## Pitfalls

- Do not enable sources with `access: scrape` in `job_sources.json`
  without the user's explicit consent — it may violate the site's terms.
- Do not try to automate LinkedIn / Indeed — there is no public
  application API, and the user's account may get blocked.
- Do not call the LLM Gateway for vacancies that did not pass
  `match_score.py` — this is the single reason the pipeline stays cheap
  under a heavy vacancy stream. Reversing the order (LLM first, filter
  second) increases model spend by an order of magnitude with no quality
  gain.
- Calibrate `match.score_threshold` together with the user in the first
  days — too low spams irrelevant items, too high skips good matches.
- `hermes_backend.py` invokes `hermes -z` as a subprocess for every LLM
  task (up to 3 calls per pre-filtered vacancy). Under a heavy stream
  this adds noticeable latency and provider model spend (openrouter).
  This is expected and matches the pipeline design (LLM is only called
  after the cheap code filter), but keep it in mind when calibrating
  `search.interval_hours`.

## Verification

- After the first run, show the user the full `JOB_SEARCH_COMPLETED`
  payload (checked/matched/great/applied) so they can adjust criteria
  or the threshold.
- Verify that messages actually reach Telegram: `python
  scripts/telegram_notify.py --test`.
- Verify that the backend is really wired: `python
  scripts/hermes_backend.py` — runs a single test call with
  task=vacancy_fit on dummy data through `hermes -z` and prints the
  result. If it fails, `llm_gateway.is_configured()` will return False
  inside `run()` and the workflow will silently degrade to code-only
  mode (not an error, but the user should know that's what is happening).
