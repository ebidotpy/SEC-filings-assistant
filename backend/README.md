# Backend

FastAPI service for Document Copilot. Config lives in `app/config.py`; the app entrypoint is `app/main.py`.

## Setup

```bash
cd backend
uv sync
cp .env.example .env   # fill in Supabase, DATABASE_URL, OpenAI
```

Required env vars are listed in `.env.example`. The app fails on startup if any are missing.

## Run

```bash
uv run uvicorn app.main:app --reload
```

- API: http://localhost:8000  
- Health: http://localhost:8000/health  
- Docs: http://localhost:8000/docs  

Alternative:

```bash
uv run python app/main.py
```

## Dev

```bash
uv run --group dev pytest tests/
uv run ruff check app ingest
```

## Ingest sample corpus

Run from `backend/` after `uv sync --group dev` and a filled `.env`.

1. Convert SEC HTML to Markdown (from repo root):

```bash
uv run --project backend --group dev python data/html_to_markdown.py
```

2. Load filings into `source_documents`:

```bash
uv run python ingest/load_source_documents.py
```

3. Chunk, embed, and load `document_chunks` (Docling HybridChunker + OpenAI embeddings):

```bash
# Free: chunk stats only
uv run --group dev python ingest/load_document_chunks.py \
  --accession-number 0000320193-25-000079 --dry-run

# Smoke test: one chunk + one embedding call
uv run --group dev python ingest/load_document_chunks.py \
  --accession-number 0000320193-25-000079 --limit-chunks 1

# Full corpus (after smoke test passes)
uv run --group dev python ingest/load_document_chunks.py --skip-existing
```

Re-run with `--skip-existing` to skip documents that already have chunks. Use `--force` to delete and re-ingest a document.

More detail: [docs/guides/backend-setup.md](../docs/guides/backend-setup.md) and [AGENTS.md](./AGENTS.md).
