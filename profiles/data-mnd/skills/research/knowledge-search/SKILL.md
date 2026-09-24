---
name: knowledge-search
description: >
  Search the DATA MIND personal knowledge base using hybrid
  (exact + semantic vector) retrieval. Use when the user asks
  about personal projects, research, decisions, or any information
  stored in the DATA MIND vault.
  Usage: python knowledge/knowledge_search.py "<query>" [--limit N]
  Returns JSON with results, provenance, and sources.
category: research
---

# Knowledge Search Skill

## When to use

Use this skill when the user asks a question about their personal knowledge base (DATA MIND). This includes:

- Projects: `zarabotok`, `crypto-card-bot`, `lichnyj-brend`, `tg-mini-games`
- Status: `What is the status of project X?`, `What am I working on now?`
- Decisions: `What did I decide about X?`
- Areas: `финансы`, `growth`, `health`
- People: `devushka`, `relationships`, `semya`
- Any question about information stored in the DATA MIND vault

## How to use

1. Run the knowledge search script:
   ```
   python knowledge/knowledge_search.py "<user query>" --limit 3
   ```

2. The script returns structured JSON with:
   - `results` — array of matching chunks with provenance
   - `sources` — formatted Sources block for the answer
   - `search_time_ms` — performance info

3. Each result contains:
   - `document` — file path (e.g. `02_Projects/zarabotok.md`)
   - `section` — heading hierarchy
   - `confidence` — LOW (unclassified), MEDIUM, or HIGH
   - `method` — exact, vector, or hybrid
   - `relevance` — score 0.0–1.0
   - `text` — the actual content

4. Always include the `sources` block in your answer.

## Example

```bash
python knowledge/knowledge_search.py "Какой статус проекта zarabotok" --limit 3
```

## Path

The script is located at:
`/c/Users/Admin/AppData/Local/hermes/profiles/data-mnd/knowledge/knowledge_search.py`

Run it from the Hermes profile directory:
`cd /c/Users/Admin/AppData/Local/hermes/profiles/data-mnd && python knowledge/knowledge_search.py`