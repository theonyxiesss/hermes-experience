---
name: knowledge-system
description: "RAG infrastructure for Hermes knowledge bases."
version: 1.0.0
author: Knowledge Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [knowledge, rag, retrieval, embeddings, faiss, hybrid-search, provenance, data-mind]
    category: research
    related_skills: [llm-wiki, grounded-citations, obsidian, knowledge-search]
---

# Knowledge System

Build and maintain a persistent knowledge retrieval infrastructure that integrates with Hermes Agent, LLM Wikis, RAG pipelines, and structured knowledge bases. This skill covers the *retrieval layer* (chunking, embedding, indexing, hybrid search, provenance) — the infrastructure that powers context-aware answers from your knowledge base.

The `knowledge/` module lives at `$HERMES_HOME/knowledge/` and is infrastructure code, not a user-facing Hermes skill. This skill documents how to build, use, and maintain it.

## When This Skill Activates

Use this skill when the task involves:

- Building or extending knowledge retrieval/RAG infrastructure for Hermes
- Integrating a knowledge base (DATA MIND, LLM Wiki, vault) with semantic search
- Setting up embeddings, vector indexes, or hybrid retrieval
- Implementing provenance tracking (source → document → confidence chains)
- Configuring chunking strategies for markdown knowledge bases
- Troubleshooting embedding/infrastructure dependencies
- Planning a multi-phase knowledge system rollout
- Any task where the user says "knowledge system", "knowledge agent", "RAG", or "retrieval"

## Architecture Methodology

**Never do premature implementation.** Follow this multi-phase approach for ALL knowledge infrastructure work:

```
PHASE 1 — AUDIT      → Inspect existing system (files, configs, skills, tools, DBs, APIs)
PHASE 2 — UNDERSTAND → Map current architecture, identify gaps, inventory existing components
PHASE 3 — DESIGN     → Design the target architecture on paper, justify every new component
PHASE 4 — PLAN       → Write implementation plan with file paths, dependencies, risks, rollback
PHASE 5 — IMPLEMENT  → Build MVP first, then iterate. Never implement everything at once.
PHASE 6 — TEST       → Unit tests + real queries against the actual knowledge base
PHASE 7 — VALIDATE   → Verify the system starts, works, doesn't break existing workflows
```

### Golden Rules (from the user, encode these)

```
1. НЕ ПРЕДПОЛАГАЙ. Сначала исследуй существующую систему.
   (Don't assume. First inspect the existing system before designing anything.)

2. Не создавай новый сервис, если существующий компонент уже решает эту задачу.
   (Don't create a new service if an existing component already solves the problem.)

3. Каждое новое технологическое решение должно иметь конкретное архитектурное обоснование.
   (Every new technology choice must have a concrete architectural justification.)

4. Не добавляй vector database, graph database, Redis, PostgreSQL, MCP server или другой
   infrastructure component только потому, что он является стандартным для RAG.
   (Don't add infrastructure components just because they're standard for RAG.)
```

## Knowledge Module Structure

The canonical layout at `$HERMES_HOME/knowledge/`:

```
knowledge/
├── __init__.py                          Package root
├── config.py                            Configuration loader (reads Hermes config.yaml)
├── types.py                             Core types: KnowledgeChunk, Provenance, enums (FACT, DECISION, etc.)
├── processor/
│   └── chunker.py                       Section-aware Markdown chunker (respects ## hierarchy, preserves wikilinks)
├── utils/
│   ├── hasher.py                        SHA256 file/string hasher for change detection
│   └── embedder.py                      sentence-transformers wrapper (lazy-load, batch encoding, L2 normalization)
├── indexer/
│   ├── metadata_store.py                SQLite store for file + chunk metadata, vector ID mappings
│   └── pipeline.py                      Incremental indexing orchestrator (change detection → chunk → embed → store → FAISS)
├── retriever/
│   ├── exact.py                         ripgrep/keyword search with heading extraction from markdown
│   ├── vector.py                        FAISS IndexFlatL2 semantic search (brute-force, good for <10K vectors)
│   └── hybrid.py                        Weighted fusion of exact + vector results with deduplication
├── assembler/
│   ├── context_builder.py               Token-aware context window assembly (confidence > type > relevance priority)
│   └── provenance_formatter.py          Sources block: [N] document → section → date → confidence → method
└── cli/
    └── knowledge_cli.py                 `python -m knowledge.cli.knowledge_cli index --full`

## Hermes Integration Layer

Hermes invokes the knowledge system via the `knowledge-search` skill, which runs:

```
python knowledge/knowledge_search.py "<query>" --limit N
```

**File:** `knowledge/knowledge_search.py` — a standalone CLI entry point that:
1. Auto-builds the FAISS index if missing (first-run convenience)
2. Accepts natural-language queries (Russian + English)
3. Returns structured JSON with results + provenance + Sources block
4. Can be invoked from any Hermes session via the terminal tool

This is the **primary integration path** — it keeps the knowledge module as infrastructure and Hermes interaction via the skill layer. Direct Python imports (see below) are for agent-authored tools and scripts, not for user-facing Hermes chat sessions.

## Choosing a Retrieval Strategy

| When user wants... | Use |
|---|---|
| Specific fact, project name, date, file, config | **Exact search** (`ExactRetriever` — ripgrep keywords) |
| Conceptual, "tell me about", similarity search | **Vector search** (`VectorRetriever` — FAISS semantic) |
| Both (default) | **Hybrid search** (`HybridRetriever` — weighted fusion) |
| Quick contextual lookups | **ContextBuilder** from any source |

## Embedding Model Selection

For multilingual knowledge bases (Russian + English):

| Model | Dimensions | Size | Quality | Use Case |
|-------|-----------|------|---------|----------|
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | ~120MB | Good | **Recommended**: best quality/size for Russian+English |
| `paraphrase-multilingual-MiniLM-L6-v2` | 384 | ~80MB | Adequate | Smaller, faster, lower quality |
| `all-MiniLM-L6-v2` | 384 | ~22MB | English only | Only for English-only vaults |

**Config key:** `knowledge.embedding_model` in config.yaml

## Index Management

**Incremental indexing (default, RECOMMENDED):**
```bash
python -m knowledge.cli.knowledge_cli index
```
Scans vault files, compares SHA256 hashes to last index, only processes new/modified files.

**Full reindex:**
```bash
python -m knowledge.cli.knowledge_cli index --full
```
Clears FAISS index AND SQLite metadata atomically, then reprocesses every file. This prevents orphaned vector IDs and stale metadata from persisting after a rebuild.

**Stats:**
```bash
python -m knowledge.cli.knowledge_cli stats
```

**Test a query:**
```bash
python -m knowledge.cli.knowledge_cli test "какой статус проекта?"
```

## Integration with Hermes

### Via SOUL.md (Knowledge Agent Identity)

The SOUL.md should contain:
- **Knowledge First** principle: search DATA MIND before answering
- **Retrieval Strategy**: exact → vector → hybrid depending on query type
- **Knowledge Classification**: FACT / DECISION / HYPOTHESIS / PREFERENCE etc.
- **Source Evaluation**: check source, document, section, timestamp, confidence
- **Provenance Requirements**: every answer cites sources with [document → section → date → confidence]
- **Contradiction Handling**: report conflicts, don't silently choose one source

### Via config.yaml

```yaml
knowledge:
  enabled: true
  vault_path: "${WIKI_PATH}"
  embedding_model: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
  chunk_size: 400
  chunk_overlap: 50
  index_path: "${HERMES_HOME}/knowledge/embeddings"
  max_context_tokens: 8192
  hybrid_weights:
    exact: 0.4
    vector: 0.6
  provenance:
    required: true
    include_timestamp: true
    include_confidence: true
```

### Python Usage (for skills or tools)

```python
from knowledge.retriever.hybrid import HybridRetriever
from knowledge.assembler.context_builder import ContextBuilder
from knowledge.assembler.provenance_formatter import ProvenanceFormatter

retriever = HybridRetriever()
results = retriever.search("какой статус проекта zarabotok?")
context = ContextBuilder().build_context(results, query="...")
sources = ProvenanceFormatter().format_sources_block(context.chunks)

# Each chunk has: text, knowledge_type, provenance
# provenance has: source, document, section, timestamp, confidence, retrieval_method, relevance_score, content_hash
```

## Provenance: Every Chunk Must Have

Every retrieved knowledge chunk must carry:

```
source          → "DATA MIND" (or whatever knowledge source)
document        → Relative path from vault root (e.g., "02_Projects/zarabotok.md")
section         → Heading hierarchy (e.g., "Рабочая модель → 4 опоры")
timestamp       → File modification time (ISO format)
confidence      → HIGH / MEDIUM / LOW
retrieval_method → EXACT / VECTOR / HYBRID
relevance_score → Normalized 0.0–1.0
content_hash    → SHA256 of chunk text (for deduplication)
```

**Confidence semantics:**
- `LOW` — **default for all unclassified chunks.** Content is NOT verified. Use as supporting evidence, not as fact. The agent should explicitly note low confidence when presenting these results.
- `MEDIUM` — information from indexed documents with some cross-referencing or verification.
- `HIGH` — explicitly verified or cross-referenced information (e.g., same fact found in multiple independent documents).

**Sources block format for answers:**
```
Sources:
[1] 02_Projects/zarabotok.md → Статус проекта → 2026-08-26 → LOW → HYBRID
[2] 08_Areas/finance.md → Текущее состояние → 2026-08-26 → LOW → VECTOR
```

## Provenance Integration with grounded-citations

The `grounded-citations` skill handles the OUTPUT side (citation ledger, evidence verification). This skill handles the INPUT side (retrieval with provenance). They work together:

- `knowledge/retriever/*` → retrieves chunks with provenance metadata
- `grounded-citations` → registers retrieved URLs/sources in a ledger, renders the Sources block, verifies citations

When producing a grounded answer: use `knowledge/retriever/` for internal knowledge retrieval, `grounded-citations` for external web sources, and merge the provenance formats compatibly.

## Chunking Rules

- **Section-aware**: Respect markdown `#` `##` `###` hierarchy. Small sections remain intact.
- **Target:** 300–500 tokens per chunk (configurable via `chunk_size` and `chunk_overlap`)
- **Preserve**: Heading hierarchy, wikilinks (`[[link]]`), code blocks, tables
- **Don't split**: Code blocks or tables unnecessarily — keep them intact even if over target size
- **Don't re-process unchanged files**: SHA256 hash comparison prevents redundant embedding

## Dependency Management

**Required packages** (install via Hermes venv's pip):

```bash
# Use the Hermes venv python, NOT the global one — otherwise imports will fail
HERMES_PYTHON="$HERMES_HOME/../hermes-agent/venv/Scripts/python.exe"  # Windows
# or:
HERMES_PYTHON="$HERMES_HOME/../hermes-agent/venv/bin/python"  # Linux/macOS

"$HERMES_PYTHON" -m pip install "numpy<2" loguru sentence-transformers faiss-cpu huggingface_hub transformers
```

**Critical compatibility constraints:**
- `faiss-cpu` was compiled with numpy 1.x — requires `numpy<2` or you get `_ARRAY_API not found` errors
- `sentence-transformers` requires `huggingface_hub` within a specific range — install all together to let pip resolve it
- `loguru` is a lightweight dependency for structured logging — install alongside

**Recommended install command** (run this exact sequence to avoid version conflicts):
```bash
"$HERMES_PYTHON" -m pip install "numpy<2" sentence-transformers faiss-cpu loguru huggingface_hub transformers
```
This lets pip resolve the full dependency tree in one pass. Installing in stages (numpy first, then sentence-transformers) causes version conflicts.

## Pitfalls

*[Full bug pattern catalogue with reproduction steps: `references/phase2-bug-patterns.md`]*

- **Never modify DATA MIND files during indexing** — vault is read-only. Read, chunk, embed, store — never write back.
- **Never modify existing Hermes skills** — knowledge module is infrastructure, not a skill. Don't touch bundled/hub skills.
- **Don't create a parallel knowledge architecture** — reuse existing `search_files`, `web_search`, `session_search`, SQLite infrastructure.
- **Don't optimize for scale prematurely** — FAISS IndexFlatL2 (brute-force) is fine for <10K vectors. No IVF/HNSW needed yet.
- **Don't implement features that belong to Phase 3+** — knowledge graph, LLM classifiers, conflict detectors, file watchers come later. MVP means minimal retrievable unit.
- **Path handling on Windows** — Use `pathlib.Path()`. Don't rely on shell variable expansion in file tools (`$WIKI_PATH` won't expand in `read_file`). Resolve paths to absolute before passing to tools.
- **Embedding model loading is lazy** — model downloads on first `embed_texts()` call, which takes 1-2 minutes for `paraphrase-multilingual-MiniLM-L12-v2`. Don't panic.
- **FAISS index + SQLite metadata must stay in sync** — if you clear one without the other, vector IDs will be orphaned. Always rebuild both (`--full` reindex).
- **The Hermes command `hermes config set knowledge.X` saves the value even if Hermes doesn't recognize the key** — custom top-level keys are bridged to the environment. Use `--force` to skip the notice.
- **FAISS returns `numpy.int64` — cast to `int()` before SQLite lookup** — `faiss.index.search()` returns `numpy.int64` arrays. When looking up chunk records via `WHERE vector_id = ?`, the numpy type is not recognized by SQLite's adapter. Always cast: `faiss_id = int(faiss_id)` before passing to SQLite. This was the root cause of "vector search returns 0 results" even though FAISS index had entries.
- **`splitlines(keep=True)` is invalid on Python 3.12+** — This was a Python 3.12 change: `str.splitlines()` now rejects `keep=True` as a keyword argument; use `splitlines(True)` (positional) instead. Blocks all indexing if the chunker uses `keep=True`.
- **`json.loads()` on already-parsed `ChunkRecord` fields** — `ChunkRecord.__init__` already parses `heading_path` and `wikilinks` from JSON strings into Python lists. Don't call `json.loads()` again on the parsed list — it will fail with "the JSON object must be str, bytes or bytearray, not list". The `_get_chunk_by_vector_id()` method returns a `ChunkRecord` with these fields already deserialized.
- **Create file record BEFORE chunk records** — The `pipeline.py` `index_file()` method must call `add_or_update_file()` BEFORE `add_chunk()`, because the chunks table has a `NOT NULL` foreign key constraint on `file_id`. If chunks are inserted first with `file_id=None`, the constraint fails. This was the root cause of "NOT NULL constraint failed: chunks.file_id" on every file during indexing.
- **MSYS path conversion on Windows** — When running under Git Bash, paths like `/c/Users/...` are passed to the Python process as-is. Python's `pathlib.Path()` on Windows treats these as relative paths (the leading `/` is not a drive letter). Add a `_to_windows_path()` static method to `config.py` that converts `/c/` → `C:/` etc. before constructing the `Path` object. Without this, `config.vault_path.exists()` returns `False` even though the vault exists.
- **Set `HERMES_HOME` in `os.environ` before importing knowledge components** — The `KnowledgeConfig` reads `${HERMES_HOME}` from environment to find the index path. If it's not set (e.g., running from a test script or bash), env var expansion produces an empty string and the index files can't be found. Set it explicitly: `os.environ["HERMES_HOME"] = str(Path("/path/to/profile").resolve())`.
- **Set `WIKI_PATH` in `os.environ` before importing** — Same issue: `.env` files are loaded by Hermes on startup, but test scripts and standalone Python runs don't auto-load them. The knowledge config reads `vault_path` from config.yaml which may contain `${WIKI_PATH}`. Without the env var, the vault path resolves to an empty string or literal `${WIKI_PATH}`. Set it explicitly: `os.environ["WIKI_PATH"] = "C:/Users/.../МояБазаЗнаний"` (use Windows-style path with forward slashes).
- **`RetrievalMethod` enum vs string in hybrid results** — When `HybridRetriever._dict_to_chunk()` creates a new `Provenance`, pass the retrieval method as a `RetrievalMethod` enum, not a string. The `Provenance` dataclass validates the field type. If you pass `"hybrid"` (string), accessing `.value` on the presumed enum will fail with `AttributeError: 'str' object has no attribute 'value'`. Use `RetrievalMethod(item["retrieval_method"])` to convert.