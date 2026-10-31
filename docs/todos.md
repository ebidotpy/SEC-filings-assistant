# Document Copilot — implementation checklist

Work top to bottom. Each phase unlocks the next. Check items off as you go.

## Where to start: backend, frontend, or both?

**Start with foundation, then backend-led vertical slices.**

| Order | Why |
| ----- | --- |
| 1. Supabase + sample data | Everything persists here; you need a project and a corpus to test against. |
| 2. Backend schema + migrations | Auth, chat, retrieval, and citations all depend on the data model. |
| 3. Thin vertical slices | Wire auth, then a stubbed chat stream, then real RAG — each slice touches frontend + backend together. |
| 4. Frontend in parallel (lightly) | Scaffold the SPA early, but don't build citation UI or chat polish until the backend can return real grounded answers. |

The critical path is **data model → ingestion → retrieval → LLM → citations**. The frontend is mostly a streaming chat shell with auth and citation display — it shouldn't get far ahead of working APIs.

---

## Phase 0 — Prerequisites & foundation

- [x] Install toolchain: Python 3.12+, `uv`, Node 20+, `pnpm` (see [README](../README.md))
- [x] Create Supabase project and collect credentials ([supabase-setup](guides/supabase-setup.md))
- [x] Create OpenAI API key (needed from Phase 6 onward)
- [x] Set `USER_AGENT` in `data/download.py` and download sample 10-K corpus:
  ```bash
  uv run data/download.py
  ```
- [x] Confirm `data/downloads/manifest.json` lists AAPL, MSFT, NVDA, AMZN, GOOGL filings (2021–2025)

---

## Phase 1 — Backend scaffold & database

Goal: a running FastAPI service with a migrated Supabase schema.

- [x] Init backend deps and project layout ([backend-setup](guides/backend-setup.md))
- [x] `app/config.py` — settings module, fail fast on missing env vars
- [x] `app/main.py` — FastAPI app, CORS, health check (`GET /health`)
- [x] SQLAlchemy models in `app/database/models/`:
  - [x] `users`
  - [x] `source_documents`
  - [x] `document_chunks` (embedding + generated `tsvector`)
  - [x] `chat_threads`
  - [x] `chat_messages`
  - [x] `message_citations`
- [x] Alembic init + first migration:
  - [x] `create extension if not exists vector`
  - [x] `vector(1536)` embedding column
  - [x] generated `tsvector` column on chunks
  - [x] HNSW index (vector) + GIN index (full-text)
  - [x] RLS policies (users see only their own chats)
- [x] `uv run alembic upgrade head` against Supabase direct connection
- [x] `app/database/supabase.py` — user-scoped and service-role clients
- [x] Verify: `uv run uvicorn app.main:app --reload` → health check returns 200

---

## Phase 2 — Auth (full stack)

Goal: analysts can sign in with email; backend rejects unauthenticated requests.

**Backend**

- [x] `app/auth/dependencies.py` — verify `Authorization: Bearer <supabase_jwt>`, expose `get_current_user`
- [x] `GET /me` (or similar) — test route that returns the authenticated user; returns `401` without a valid token
  - Done: `app/api/auth.py` on `protected_router`
- [x] Reject missing/expired tokens with `401` before any chat or retrieval work
  - Done: `app/api/router.py` — router-level `Depends(get_current_user)`; future chat/retrieval routes register here

**Frontend**

- [x] Scaffold Vite + React + TypeScript + Tailwind + shadcn ([frontend-setup](guides/frontend-setup.md))
  - Done: deps installed, `@/` alias, Tailwind v4, shadcn `components.json`, `.env.example`
- [x] `src/lib/env.ts` — validate `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
- [x] `src/lib/supabase.ts` — browser Supabase client
- [x] `src/lib/http.ts` + `src/lib/api.ts` — fetch wrapper with automatic bearer token
- [x] Sign-in / sign-up pages (email only, no SSO)
- [x] Protected routes — redirect unauthenticated users to login
- [x] Verify: sign up, sign in, token reaches backend on a test authenticated endpoint

---

## Phase 3 — Chat shell (vertical slice, stubbed)

Goal: end-to-end chat UI streaming from FastAPI, no real retrieval yet.

**Backend**

- [x] Chat thread CRUD: list threads, create thread, load message history
- [x] `POST /chat/stream` — accepts AI SDK message format, streams a stubbed assistant reply
- [x] Persist user + assistant messages to `chat_messages` after stream completes
- [x] `403` when user accesses another user's thread

**Frontend**

- [x] React Router: login, chat list, chat thread routes
  - Done: `/sign-in`, `/sign-up`, `/chat`, `/chat/:threadId` in `frontend/src/App.tsx`
- [x] AI SDK chat primitives pointed at `POST /chat/stream` with Supabase bearer token
  - Done: `useChat` + `DefaultChatTransport` in `frontend/src/pages/chat/ChatThreadPage.tsx`
- [x] Thread sidebar (past conversations)
  - Done: `frontend/src/components/chat/ThreadSidebar.tsx` + `GET/POST /chat/threads`
- [x] Basic message list + input + streaming indicator
  - Done: `MessageList`, `ChatInput`, `StreamingIndicator` under `frontend/src/components/chat/`
- [x] Verify: create thread, send message, see streamed stub response, reload and see history
  - Done: `pnpm tsc`, `pnpm lint`, `pnpm build` pass; manual browser check with backend on `:8000`

---

## Phase 4 — Ingestion pipeline

Goal: SEC filings in the corpus are parsed, chunked, embedded, and stored in Supabase.

- [x] `ingest/` scripts (or CLI entrypoint) for one-off corpus loading
  - Done: `backend/ingest/chunking.py`, `embeddings.py`, `load_document_chunks.py`
- [x] HTML → normalized Markdown extraction (preserve page/section metadata)
  - Done: `data/html_to_markdown.py` converts `data/downloads/` → `data/Markdown/` via Docling
- [x] Chunking strategy (size + overlap; store chunk index, page, section, ticker, filing type, year)
  - Done: Docling `HybridChunker` (512-token target, OpenAI tokenizer) over local Markdown → `DoclingDocument`
- [x] Write `source_documents` rows with filing metadata from `manifest.json`
  - Done: `backend/ingest/load_source_documents.py` loads `data/Markdown/manifest.json` into Supabase
- [x] Write `document_chunks` rows with text + metadata
  - Done: `backend/ingest/load_document_chunks.py` (smoke-tested with `--limit-chunks 1`)
- [x] OpenAI embedding generation → store `vector(1536)` per chunk
  - Done: `backend/ingest/embeddings.py` using `text-embedding-3-small`
- [x] Generated `tsvector` populated for full-text search
  - Done: Postgres generated column on insert (no app code needed)
- [x] Idempotent re-run (skip already-ingested documents)
  - Done: `--skip-existing` / `--force` on `load_document_chunks.py`
- [x] Unit tests: chunking logic, metadata extraction
  - Done: `backend/tests/ingest/test_chunking.py`, `test_load_document_chunks.py`
- [x] Run ingestion on full sample corpus (25 filings × 5 companies)
- [x] Verify: chunks exist in Supabase; spot-check a known passage (e.g. Apple revenue mix table)

---

## Phase 5 — Retrieval

Goal: a user question returns ranked, relevant source passages.

- [x] `retrieval/queries.py` — pgvector semantic search over `document_chunks`
  - Done: `backend/app/database/documents.py` (`semantic_search_chunk_ids`) + `backend/app/retrieval/queries.py` (parallel hybrid wrapper)
- [x] `retrieval/queries.py` — Postgres full-text search over `search_vector`
  - Done: `backend/app/database/documents.py` (`fulltext_search_chunk_ids` via `plainto_tsquery` + `ts_rank_cd`)
- [x] `retrieval/fusion.py` — Reciprocal Rank Fusion in Python
  - Done: `backend/app/retrieval/fusion.py` (`reciprocal_rank_fusion`, k=60)
- [x] `retrieval/retriever.py` — query → fused ranked passages + neighbor chunks
  - Done: `backend/app/retrieval/retriever.py` (`DocumentRetriever.search`, `get_chunk`, `get_surrounding_chunks`)
- [x] Unit tests: fusion ranking, query assembly (mock DB)
  - Done: `backend/tests/retrieval/test_fusion.py`, `test_queries.py`, `test_retriever.py`
- [x] Integration test (optional, `@pytest.mark.integration`): real query against ingested corpus
  - Done: `backend/tests/retrieval/test_integration.py` (Apple revenue mix, NVIDIA Data Center; requires ingested corpus)
- [x] Verify: test queries from [client-brief](client-brief.md) return relevant chunks (manual or scripted)
  - Done: `backend/scripts/verify_retrieval.py` — run after Phase 4 corpus ingest, e.g. `uv run python scripts/verify_retrieval.py "Apple revenue mix 2021-2025" --ticker AAPL`

---

## Phase 6 — LLM agent & grounding

Goal: grounded answers with enforced citations — the core product contract.

- [x] `assistant/instructions.md` — product contract (cite everything, refuse to invent, no stock picks)
  - Done: `backend/app/assistant/instructions.md`
- [x] PydanticAI agent with typed deps (`DocumentAgentDeps`) and output (`GroundedAnswer`)
  - Done: `backend/app/assistant/agent.py`, `deps.py`, `outputs.py`
- [x] Agent tools: `search_filings`, `read_chunk`, `read_surrounding_chunks`
  - Done: `backend/app/assistant/tools.py` wrapping `DocumentRetriever`
- [x] `chat/orchestrator.py` — one turn: retrieve → agent → validate → stream → persist
  - Done: `backend/app/chat/orchestrator.py` (`run_grounded_turn`)
- [x] `grounding/validator.py` — every citation maps to a retrieved passage; fail closed on violation
  - Done: `backend/app/grounding/validator.py`
- [x] `chat/streaming.py` — AI SDK-compatible stream (text deltas + citation metadata parts)
  - Done: `backend/app/chat/streaming.py` (`data-citations` parts + SSE v1)
- [x] Persist `message_citations` linked to assistant messages
  - Done: `backend/app/database/chats.py` (`insert_citations`, hydrate on load)
- [x] Unit tests: citation validation, grounding enforcement, message conversion
  - Done: `backend/tests/grounding/`, `backend/tests/assistant/`, `backend/tests/chat/`
- [x] Verify against [client-brief example questions](client-brief.md#example-analyst-questions):
  - Done: `backend/scripts/verify_agent.py` + `backend/tests/chat/test_agent_integration.py` (requires ingested corpus + OpenAI)
  - [x] Answers cite specific filings and pages (manual after ingest)
  - [x] Under-specified questions get "not enough evidence" responses (manual after ingest)
  - [x] Question 10 (generative AI margins) refuses to infer beyond filings (manual after ingest)

---

## Phase 7 — Trust UI (citations & source passages)

Goal: analysts can verify every claim in one click — this is what makes the product usable.

- [x] Citation chips/links on assistant messages (company, filing type, date, page/section)
- [x] Source passage panel — show underlying excerpt for selected citation
- [x] Empty states (no threads, no corpus match)
- [x] Error states (auth expired, retrieval failure, grounding failure, network/CORS)
- [x] Loading/streaming status during assistant run
- [x] Verify: click a citation → see the exact passage from the filing

---

## Phase 8 — Pilot readiness

Goal: 5 senior analysts can use it for a week and report ≥3 hours saved per analyst per week.

- [x] README "Running locally" section — copy-paste commands for backend + frontend + env vars
- [x] Seed or document how to ingest/update the corpus
- [x] Smoke-test all 10 example questions from the client brief
- [x] Confirm chat history persists across sessions
- [x] Confirm ~40-user scale assumptions (no hardcoded single-user shortcuts)
- [x] Basic structured logging on backend (`structlog`) for debugging failed turns
- [x] Review latency: streaming starts within a few seconds for typical queries

---

## Phase 9 — Deployment (Railway)

- [ ] Railway: backend service (Uvicorn, env vars, `ALLOWED_ORIGINS`)
- [ ] Railway: frontend service (Vite build, `VITE_*` env vars at build time)
- [ ] Supabase: re-enable email confirmation for production if disabled during dev
- [ ] Run `alembic upgrade head` against production Supabase (direct connection)
- [ ] Run ingestion against production database
- [ ] End-to-end test on deployed URLs with a real Driftwood-style email account

---

## Quick reference

| Doc | Purpose |
| --- | ------- |
| [client-brief.md](client-brief.md) | What Driftwood needs and example questions |
| [architecture.md](architecture.md) | System design, data model, streaming contract |
| [guides/supabase-setup.md](guides/supabase-setup.md) | Hosted Postgres + Auth |
| [guides/backend-setup.md](guides/backend-setup.md) | FastAPI + Alembic commands |
| [guides/frontend-setup.md](guides/frontend-setup.md) | Vite + React scaffold commands |
| [guides/railway-setup.md](guides/railway-setup.md) | From-zero Railway prerequisites (start here for Phase 9) |
| [guides/railway-deployment.md](guides/railway-deployment.md) | Production deployment on Railway |
