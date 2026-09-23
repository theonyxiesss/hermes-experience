# Why these folders are skipped during ingestion

| Folder | Reason |
|--------|--------|
| `.obsidian` | Obsidian config/plugins/themes — not user content |
| `.git` | Version control metadata |
| `archives` | Archived/completed projects — low retrieval value, high noise |
| `.trash` | Deleted files (Obsidian trash) |
| `inbox` | Unprocessed raw notes — not yet structured knowledge |

## Rationale
- **Signal-to-noise**: Config, git, trash, and inbox dilute semantic search with irrelevant vectors
- **Freshness**: Archives/inbox contain stale or incomplete thoughts — better to ingest only "promoted" notes
- **Performance**: Fewer chunks = faster ingestion, smaller index, lower memory

## Customization
Edit `skip_dirs` in `iter_vault_files()` to match your vault structure:
```python
skip_dirs = {".obsidian", ".git", "archives", ".trash", "inbox", "templates", "attachments"}
```