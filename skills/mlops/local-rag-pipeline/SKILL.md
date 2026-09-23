---
name: local-rag-pipeline
description: Local RAG over Markdown with ChromaDB.
trigger: User wants semantic search / RAG on a local Markdown knowledge base.
---

# Local RAG Pipeline for Markdown Vaults

Minimal, dependency-light RAG for personal knowledge bases. No cloud APIs, no heavy frameworks.

## When to use
- User has a folder of `.md` files and wants "ask my notes" capability
- Obsidian / Zettelkasten / PARA vaults
- Offline-first, privacy-sensitive, or cost-free requirement
- Quick prototype before committing to a managed service

## Architecture
```
.vault/                 # source Markdown
  ├── 01_Concept/
  ├── 02_Projects/
  └── ...
.chroma/                # ChromaDB persistent storage (auto-created)
rag_ingest.py           # single-file CLI: ingest + query
requirements-rag.txt    # chromadb, sentence-transformers, torch
```

## Core components

### 1. Ingestion (`rag_ingest.py` → `ingest()`)
- Walks vault, skips `.obsidian`, `.git`, `archives`, `inbox`
- Strips YAML frontmatter (`--- ... ---`)
- Chunks by Markdown headers (`# ## ###`) + sliding window fallback
- Embeds with `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, ru+en, fast on CPU)
- Upserts into ChromaDB collection `data_mind` with cosine HNSW index
- Metadata: `source` (relative path), `chunk_index`, `char_len`

### 2. Query (`rag_ingest.py "question"`)
- Embeds question with same model
- `coll.query(n_results=5, include=["documents","metadatas","distances"])`
- Returns top-k with similarity scores (1 - cosine distance)

## Quick start
```bash
cd /path/to/vault/parent
python -m pip install -r requirements-rag.txt
python rag_ingest.py              # ingest
python rag_ingest.py "your question"  # query
```

## Configuration knobs (edit top of `rag_ingest.py`)
| Constant | Default | When to change |
|---|---|---|
| `VAULT_ROOT` | `./МояБазаЗнаний` | Different folder name |
| `CHROMA_DIR` | `./.chroma` | Separate disk / shared index |
| `COLLECTION_NAME` | `data_mind` | Multiple collections per vault |
| `EMBED_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Different language / quality trade-off |
| `CHUNK_SIZE` | 500 tokens (~2000 chars) | Longer/shorter context window |
| `CHUNK_OVERLAP` | 50 tokens | More/less overlap between chunks |

## Model alternatives
| Model | Dim | Lang | Speed | Quality |
|---|---|---|---|---|
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | 50+ | ★★★★★ | Good |
| `all-MiniLM-L6-v2` | 384 | en | ★★★★★ | Good (en only) |
| `BAAI/bge-m3` | 1024 | 100+ | ★★★☆☆ | Best |
| `intfloat/multilingual-e5-large` | 1024 | 100+ | ★★☆☆☆ | Best |

## Pitfalls & fixes
- **`ModuleNotFoundError: chromadb`** → run `pip install chromadb` in the *same* interpreter that runs the script (check `which python`)
- **HF Hub rate limit warning** → set `HF_TOKEN` env var or `huggingface-cli login`
- **ChromaDB `InvalidCollectionException`** → delete `.chroma/` and re-ingest (schema mismatch after version upgrade)
- **Empty results** → check `VAULT_ROOT` path, ensure `.md` files exist outside skipped dirs
- **Slow first run** → model downloads ~400 MB on first `SentenceTransformer()` call; subsequent runs use cache

## Extending
- **Watchdog re-ingest**: cron job / file watcher → call `ingest()` on changes
- **API server**: wrap `query()` in FastAPI + `/ask` endpoint
- **Hybrid search**: add BM25 (rank-bm25) + reciprocal rank fusion
- **Reranker**: cross-encoder (`BAAI/bge-reranker-base`) on top-k
- **Multi-vault**: separate collections or `namespace` in metadata

## Verification checklist
- [ ] `python rag_ingest.py` exits 0, prints vector count > 0
- [ ] `python rag_ingest.py "known topic"` returns relevant chunks from vault
- [ ] Scores 0.35–0.55 for relevant, <0.25 for noise
- [ ] Russian queries work (multilingual model)

## Files in this skill
- `scripts/rag_ingest.py` — the canonical single-file pipeline (copy to vault root)
- `templates/requirements-rag.txt` — pinned deps
- `references/obsidian-skip-dirs.md` — rationale for skipped folders