# Data

Local data artifacts for development live here.

- `downloads/` holds raw source files fetched from SEC EDGAR, grouped by year.
- `Markdown/` holds Docling-converted Markdown with the same year layout and manifest.
- Downloaded payloads are gitignored because the corpus can get large.

## Corpus pipeline

From repo root:

```bash
uv run data/download.py
uv run --project backend --group dev python data/html_to_markdown.py
```

From `backend/`:

```bash
uv run python ingest/load_source_documents.py
uv run --group dev python ingest/load_document_chunks.py --skip-existing
```

Use `--dry-run` and `--limit-chunks 1` on `load_document_chunks.py` before running the full embedding pass.
