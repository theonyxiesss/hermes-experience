# Phase 2 Bug Patterns Catalogue

Debugging reference for the knowledge retrieval MVP. All bugs below were discovered during Phase 2 end-to-end validation against a real DATA MIND vault.

## Indexing Blockers

### 1. `splitlines(keep=True)` → `AttributeError: 'keep' is an invalid keyword argument`

**File:** `processor/chunker.py`
**Python 3.12+ change:** `str.splitlines()` no longer accepts `keep=True` as a keyword argument. Use positional: `splitlines(True)`.
**Symptom:** Every file fails with this error during indexing. No chunks are created.
**Fix:** `lines = text.splitlines(True)` (positional, not keyword)

### 2. `NOT NULL constraint failed: chunks.file_id` on every file

**File:** `indexer/pipeline.py` → `index_file()`
**Root cause:** The method calls `add_chunk()` with `file_id=None` (because the file record hasn't been created yet), then creates the file record afterwards. The chunks table has a `NOT NULL` foreign key constraint on `file_id`.
**Symptom:** Indexing proceeds but every file fails with this SQLite constraint error. Embeds are generated but never stored.
**Fix:** Move `add_or_update_file()` BEFORE the chunk loop. Get the `file_id` first, then pass it to `add_chunk()`.

### 3. Missing `from datetime import datetime`

**File:** `indexer/pipeline.py`
**Symptom:** `NameError: name 'datetime' is not defined` when trying to use `datetime.fromtimestamp()` in `_chunks_to_knowledge_chunks()`.
**Fix:** Add `from datetime import datetime` to imports.

## Path Issues

### 4. MSYS paths not recognized by Windows pathlib

**File:** `config.py` → `vault_path` property
**Symptom:** `config.vault_path.exists()` returns `False` even though the vault exists. The path stored in config.yaml is `/c/Users/Admin/Documents/...` (MSYS/Git Bash format), which Python's `pathlib.Path` interprets as a relative path, not a Windows absolute path.
**Fix:** Add a `_to_windows_path()` static method:
```python
@staticmethod
def _to_windows_path(path_str: str) -> str:
    import re
    match = re.match(r'^/([a-zA-Z])/(.*)', path_str)
    if match:
        return f"{match.group(1).upper()}:/{match.group(2)}"
    return path_str
```
Apply to both `vault_path` and `index_path` properties.

### 5. Environment variables not set in Python

**Symptom:** `config.vault_path` resolves to `${WIKI_PATH}` (literal string) or empty string. The `.env` file is loaded by Hermes on startup, but standalone Python scripts don't auto-load it.
**Fix:** Before importing any knowledge module, set required env vars:
```python
os.environ["WIKI_PATH"] = "/path/to/your/vault"
os.environ["HERMES_HOME"] = str(Path("/path/to/hermes/profile").resolve())
```

## Retrieval Blockers

### 6. Vector search returns 0 results — FAISS has entries but SQLite can't find them

**File:** `retriever/vector.py` → `_faiss_result_to_knowledge_chunk()`
**Root cause:** `faiss.index.search()` returns `numpy.int64` values for the indices. SQLite's Python adapter doesn't know how to bind `numpy.int64` to a `WHERE vector_id = ?` parameter — it produces no match even though the integer value is correct.
**Symptom:** FAISS index has 187 vectors, search returns valid indices with low distances, but `_get_chunk_by_vector_id()` returns `None` for every result. The log shows "No chunk record found for FAISS ID X" for every result.
**Fix:** Cast to Python `int` before SQLite lookup: `faiss_id = int(faiss_id)`.

### 7. `json.loads()` on already-parsed list

**File:** `retriever/vector.py` → `_faiss_result_to_knowledge_chunk()`
**Root cause:** `ChunkRecord.__init__` (in `metadata_store.py`) already parses `heading_path` and `wikilinks` from JSON strings into Python lists during construction. The vector retriever then calls `json.loads()` on the already-parsed list, which fails with "the JSON object must be str, bytes or bytearray, not list".
**Symptom:** Every FAISS result silently fails conversion, returning 0 results.
**Fix:** Remove the redundant `json.loads()` calls — use `chunk_record.heading_path` and `chunk_record.wikilinks` directly (they're already lists).

### 8. `RetrievalMethod` enum vs string in hybrid results

**File:** `retriever/hybrid.py` → `_dict_to_chunk()`
**Root cause:** The `_dict_to_chunk` method passes `item["retrieval_method"]` (a string like `"hybrid"`) as the `retrieval_method` field of `Provenance`, which expects a `RetrievalMethod` enum. When the calling code tries to access `.value` on what it thinks is an enum, it gets `AttributeError: 'str' object has no attribute 'value'`.
**Symptom:** Vector search returns 3 results, but the test harness crashes on the first `.value` access.
**Fix:** Convert the string to an enum: `RetrievalMethod(item["retrieval_method"])` if the value is a string.

## Performance Notes

### Cold Start vs Warm Queries

| Operation | Cold (first call) | Warm (subsequent) |
|-----------|-------------------|-------------------|
| model loading + embedding | ~7s | N/A (loaded once) |
| single vector search | ~50ms | ~5ms |
| single exact search | ~25ms | ~25ms |
| full vault indexing (25 files) | ~13s | N/A |
| incremental reindex | ~0.03s | ~0.03s |

The cold start cost is:
- Model loading: ~6s (download + cache check)
- First embedding: ~1s (model warm-up)
- Subsequent embeddings: ~2ms per chunk

### Test Environment

- Python 3.11.15 (Hermes venv, Windows)
- sentence-transformers 6.0.0 + paraphrase-multilingual-MiniLM-L12-v2
- faiss-cpu 1.7.4 + numpy 1.26.4
- 25 .md files → 187 chunks → 187 vectors, 384-dim

## Retrieval Quality

### 9. Exact search misses natural-language queries

**Problem:** Passing a full conversational query like "Какой текущий статус проекта zarabotok?" to ripgrep returns zero matches — the entire sentence is treated as a literal string.

**Fix:** The `ExactRetriever` must extract keywords from NL queries first. The `_extract_keywords()` method in `knowledge/retriever/exact.py`:
1. Strips Russian and English stop words (какой, какие, мой, у, в, на, и, а, но, не, the, a, is, are, what, my, etc.)
2. Returns up to 3 queries: the original sentence, keyword-only string, and top individual keywords
3. Each query is searched independently, results are deduplicated by file path + line number

**Without this:** Exact search is effectively broken for any user query that's a complete sentence rather than a keyword list.