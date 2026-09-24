# Hermes Agent — Learned Experience

The memory, personality and skills that my AI agent [Hermes](https://github.com/NousResearch/hermes-agent) developed while being trained on real tasks. This is not a fork of Hermes. It is a snapshot of experience: what the agent wrote into its own long-term memory and the skills it built for itself.

## Principles the agent learned

From its long-term memory (`memories/`):

- **No fabrication.** Never invent names, URLs, metrics or clients. An honest `PARTIAL` or `FAILURE` beats fake completeness.
- **Real tools only:** curl, oEmbed, real APIs. No mocks.
- **Evidence for every claim**, with explicit statuses: `VERIFIED / PARTIAL / UNKNOWN / FAILURE`.
- **Anti-confirmation bias:** always look for contradicting evidence.
- **Honest reporting** of limitations and bottlenecks.
- Concise, fact-based reports.

## Skills

### 💼 JobHunter — `skills/career/jobhunter`
Automated job search. It collects vacancies from many sources, filters them cheaply in code, and sends ambiguous cases to an LLM for vacancy analysis and CV matching. It then drafts a personalized application, sends it to Telegram and can optionally apply through the hh.ru API.
- 0–100 match score with a notification threshold (default 70)
- Scheduled runs (default every 3 hours)
- Details: `ARCHITECTURE.md`, `PROTOCOL.md`

### 🔍 GDIR (Goal-Driven Research) — `skills/research/goal-driven-research`
Research that starts from a goal (for example, "find 10 potential clients…") and runs a pipeline: **Discovery → Enrichment → Signal Detection → Qualification → Verification**. Every candidate is checked against real sources, and results are saved with a verification status. Includes scripts for structured HTML extraction, official-website enrichment and public YouTube channel research.

### 🎯 Lead Signal Engine — `skills/research/lead-signal-engine`
A commercial reasoning layer on top of GDIR. It separates an "interesting entity" from a "qualified lead": it detects commercial signals, qualifies them with strict rules and keeps an evidence trail for every decision. The repo includes a real end-to-end test with an honest result: `PARTIAL`, 5 found, 0 fabricated.

### 📚 Local RAG Pipeline — `skills/mlops/local-rag-pipeline`
A minimal offline RAG over a Markdown knowledge base (Obsidian / PARA / Zettelkasten), built on ChromaDB and sentence-transformers. One CLI file for indexing and querying, with no cloud APIs.

## DATA MIND profile — `profiles/data-mnd/`

A separate agent persona for working with a personal knowledge base, following a **Knowledge First** rule: before answering about projects or decisions, the agent searches the knowledge base and cites the source.

- `SOUL.md`: persona instructions covering source priority, search order and citation format
- `knowledge/`: the retrieval code. Markdown chunking, embeddings, a FAISS index, hybrid search (exact + vector) and context assembly with provenance
- `skills/research/knowledge-system`: how to build and maintain this infrastructure, including a write-up of bugs found along the way
- `skills/research/knowledge-search`: a skill for quick knowledge-base search

## Layout

```
SOUL.md                  base agent personality
memories/                long-term memory (rules and preferences)
skills/                  skills created by the agent
profiles/data-mnd/       DATA MIND profile: SOUL, memory, skills, knowledge/ code
```

## Installation

Copy the files into your Hermes folder (`%LOCALAPPDATA%\hermes` on Windows, `~/.hermes` on Linux/macOS):

- `skills/*` → `<hermes>/skills/`
- `profiles/data-mnd/*` → `<hermes>/profiles/data-mnd/`

No API keys or tokens are included. Set the required variables (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `HH_ACCESS_TOKEN`, `WIKI_PATH`, etc.) in your own `.env`.

## Intentionally excluded

Keys (`.env`, `auth.json`), session history (`state.db`), logs, caches and the vector index of personal notes.
