# Document analyser

An internal AI chatbot that lets analysts query a corpus of documents in plain English and get sourced, citable answers.

## The client

**Document analyser** — fictional independent investment research firm. Their analysts spend half their week reading 10-Ks and 10-Qs before they can produce any original analysis. Document Copilot eats that intake work so they can skip straight to insight.

Full brief: [docs/client-brief.md](docs/client-brief.md)

## Stack

| Layer              | Choice                                               |
| ------------------ | ---------------------------------------------------- |
| Backend            | Python + FastAPI                                     |
| Frontend           | Vite + React SPA + TypeScript                        |
| Database           | Supabase Postgres (users, chats, documents, chunks)  |
| Migrations         | SQLAlchemy models + Alembic                          |
| Retrieval          | Supabase `pgvector` + Postgres full-text search      |
| Auth               | Supabase Auth (email only)                           |
| Hosting            | Railway                                              |
| LLM + embeddings   | OpenAI                                               |

## Repo layout

```text
document-copilot/
├── AGENTS.md           # agent instructions (read first)
├── README.md           # this file
├── data/               # local corpus + download script (payloads gitignored)
├── docs/
│   └── client-brief.md # the client one-pager
├── backend/            # FastAPI service
└── frontend/           # React SPA (Vite)
```

## Prerequisites

Install these before setting up `backend/` or `frontend/`:

| Tool | Version | Used for | Install |
| ---- | ------- | -------- | ------- |
| [Python](https://www.python.org/downloads/) | 3.12+ | Backend runtime | OS package manager or python.org |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | latest | Backend deps + `data/download.py` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Node.js](https://nodejs.org/) | 20+ (LTS) | Frontend toolchain | nodejs.org or `nvm install --lts` |
| [pnpm](https://pnpm.io/installation) | latest | Frontend package manager | `corepack enable && corepack prepare pnpm@latest --activate` |

You also need accounts/keys for external services once the app is wired up. Start with [docs/guides/supabase-setup.md](docs/guides/supabase-setup.md) (account + project), then create an [OpenAI API key](https://platform.openai.com/api-keys) when the LLM layer is wired up.

## Running locally

Install the [prerequisites](#prerequisites) (Python 3.12+, `uv`, Node 20+, `pnpm`) and create a Supabase project + OpenAI key first ([Supabase guide](docs/guides/supabase-setup.md)). Then run the backend and frontend in two terminals.

### Backend (FastAPI)

```bash
cd backend
cp .env.example .env          # fill in Supabase + OpenAI values
uv sync
uv run alembic upgrade head   # apply schema to Supabase (direct connection)
uv run uvicorn app.main:app --reload
```

Health check: `http://localhost:8000/health` returns `{"status": "ok"}`. See [docs/guides/backend-setup.md](docs/guides/backend-setup.md) for details.

### Frontend (Vite + React)

```bash
cd frontend
cp .env.example .env          # fill in VITE_API_BASE_URL, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
pnpm install
pnpm dev
```

App: `http://localhost:5173`. See [docs/guides/frontend-setup.md](docs/guides/frontend-setup.md) for details.

### Corpus

The bot only returns grounded answers once the corpus is ingested. Download and convert the sample filings (see [Sample SEC data](#sample-sec-data) below), then load them into Supabase with the `backend/ingest/` scripts (run from `backend/`):

```bash
uv run --group dev python ingest/load_source_documents.py
uv run --group dev python ingest/load_document_chunks.py
```

## Deploying to Railway

Follow [docs/guides/railway-deployment.md](docs/guides/railway-deployment.md) for the complete production deployment procedure, including the two-service monorepo setup, frontend static server, environment variables, Supabase Auth, migrations, corpus ingestion, and end-to-end checks.

## Sample SEC data

Use the standalone downloader to fetch a small local 10-K sample from SEC EDGAR.
Edit the params at the top of `data/download.py`, especially `USER_AGENT`, then run:

```bash
uv run data/download.py
```

By default this downloads the latest 5 10-K filings for AAPL, MSFT, NVDA, AMZN, and GOOGL into year folders under `data/downloads/` and writes a `manifest.json`.
Downloaded files are gitignored; the `data/` folder itself stays in git for the script and notes.

Convert those HTML filings to Markdown (same year layout + manifest) with Docling:

```bash
uv run --project backend --group dev python data/html_to_markdown.py
```

Output lands in `data/Markdown/`; converted payloads are gitignored like the raw downloads.
