# Hermes Agent — накопленный опыт

Память, личность и навыки, которые мой агент [Hermes](https://github.com/NousResearch/hermes-agent) выработал в процессе обучения.

## Структура

| Путь | Что это |
|---|---|
| `SOUL.md` | Базовая личность агента |
| `memories/MEMORY.md`, `memories/USER.md` | Долговременная память: правила работы и предпочтения |
| `skills/career/jobhunter` | Поиск вакансий: сбор, скоринг, уведомления в Telegram |
| `skills/research/goal-driven-research` | GDIR — исследование с проверкой фактов (VERIFIED / PARTIAL / FAILURE) |
| `skills/research/lead-signal-engine` | Поиск и квалификация лидов по сигналам |
| `skills/mlops/local-rag-pipeline` | Локальный RAG-пайплайн (индексация Obsidian) |
| `profiles/data-mnd/` | Профиль «DATA MIND»: SOUL, память, навыки knowledge-system / knowledge-search и код поиска по базе знаний |

## Как установить

Скопируйте файлы в папку Hermes (`%LOCALAPPDATA%\hermes` на Windows, `~/.hermes` на Linux/macOS):

- `skills/*` → `<hermes>/skills/`
- `profiles/data-mnd/*` → `<hermes>/profiles/data-mnd/`

Ключей API и токенов здесь нет — задайте их в своём `.env`.
