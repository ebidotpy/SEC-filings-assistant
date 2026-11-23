# Document Copilot — SEC filings assistant

A chatbot for querying a corpus of SEC filings and receiving answers with citations to retrieved source passages. Answers pass citation validation before they are streamed or saved.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12+ and FastAPI |
| Frontend | Vite, React SPA, TypeScript, and Tailwind CSS |
| Database | PostgreSQL with pgvector |
| Migrations | SQLAlchemy and Alembic |
| Retrieval | Vector search and PostgreSQL full-text search, fused with Reciprocal Rank Fusion |
| Authentication | Native email/password authentication with bcrypt and JWT |
| Models | OpenAI-compatible chat and embedding APIs |
| Server deployment | GitHub Actions, uv, Supervisor, and Nginx |

The project brief is in [docs/client-brief.md](docs/client-brief.md). Read [AGENTS.md](AGENTS.md) before changing code.

## Run locally

Install Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 24, [pnpm](https://pnpm.io/), and Docker Compose. Obtain an OpenAI API key, or a key for your configured OpenAI-compatible provider.

Start the local database from the repository root:

```bash
docker compose up -d postgres
```

The development database listens on port `5434`. Its default credentials are for local development; production should use a separate database and credentials.

### Backend

```bash
cd backend
cp .env.example .env
```

Fill in `OPENAI_API_KEY` and replace `JWT_SECRET_KEY` with a random secret. Generate one with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

`DATABASE_URL`, `JWT_SECRET_KEY`, and `OPENAI_API_KEY` are required. Startup rejects missing values and the example JWT secret. The example database URL matches Docker Compose. Set `BASE_URL` if using an alternative provider.

```bash
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`; `/api/health` returns `{"status":"ok"}`. This endpoint checks that the application is responding; it does not check database or model availability.

### Frontend

In a second terminal:

```bash
cd frontend
cp .env.example .env
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://localhost:5173`. Set `VITE_API_BASE_URL=/api`: Vite proxies API requests to the backend in development. Production must either proxy `/api/` to the backend or build with an absolute backend API URL, including its `/api` prefix. For separate origins, add the frontend origin to backend `ALLOWED_ORIGINS`.

Register an account in the app. Passwords must be at least six characters and at most 72 UTF-8 bytes, the bcrypt limit.

## Load the corpus

Edit `USER_AGENT` in `data/download.py` to include your contact information, then run from the repository root:

```bash
uv run data/download.py
uv run --project backend --group dev python data/html_to_markdown.py
```

The downloader fetches sample 10-K filings for AAPL, MSFT, NVDA, AMZN, and GOOGL. Downloaded and converted payloads are gitignored.

Load the converted filings from `backend/`:

```bash
uv run python ingest/load_source_documents.py
uv run python ingest/load_document_chunks.py
```

Chunk ingestion commits each complete filing as one transaction. `--force` replaces a filing's chunks after embeddings are generated. PostgreSQL prevents replacement of chunks already referenced by saved citations, preserving those citations.

## Checks

From `backend/`:

```bash
uv run pytest -m "not integration" -q
uv run ruff check .
uv run ruff format . --check
```

The unit suite uses mock service boundaries and needs no live database or API key. Integration tests require a test database with migrations applied; model integration checks may also require provider credentials and ingested data.

From `frontend/`:

```bash
pnpm tsc --noEmit
pnpm lint
pnpm build
```

Frontend behavior is verified manually in the browser. There is no frontend test runner.

## Deploy to your server

See [docs/guides/server-deployment.md](docs/guides/server-deployment.md) for the current manual deployment workflow, server prerequisites, secrets, and verification.

The repository also contains Dockerfiles for backend and frontend builds. Set `VITE_API_BASE_URL` when building the frontend image. Existing Supabase and Railway guides describe earlier deployment setups; the current application uses native authentication and PostgreSQL.
