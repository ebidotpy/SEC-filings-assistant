# Railway setup — start here (from zero)

This is the **from-zero** companion to [railway-deployment.md](railway-deployment.md).
Read this one first. It answers "what is Railway, what accounts and tools do I
need, and what do I have to gather" — in plain language, assuming you have never
used Railway before.

Once you have finished the checklist at the bottom of this page, switch to
[railway-deployment.md](railway-deployment.md) for the click-by-click service
creation, variables, migrations, and the end-to-end test.

---

## 1. The mental model — what actually gets deployed

Document Copilot is **not** a single app. It is four pieces, and only two of
them live on Railway:

| Piece | Where it runs | What it is |
| --- | --- | --- |
| **Backend** | Railway service #1 | FastAPI/Uvicorn from `/backend`. Serves the API, runs the LLM agent, talks to the database. |
| **Frontend** | Railway service #2 | The Vite/React build from `/frontend`, served as static files by Caddy. |
| **Database + Auth** | **Supabase** (not Railway) | Postgres (with `pgvector`), user accounts, and email login. |
| **LLM + embeddings** | **OpenAI** (not Railway) | Generates answers and vector embeddings. |

Key consequences of this model — read these twice:

- **Railway hosts two services from one GitHub repo.** Each service has its own
  "root directory" (`/backend` and `/frontend`) so they build independently.
- **Do NOT create a Postgres database on Railway.** Supabase stays the database.
  Railway only runs your application code.
- **The backend holds all the secrets.** The frontend is a public static bundle —
  anything you give it (every `VITE_*` value) ends up readable in the browser.
  Never put the Supabase service-role key, the database URL, or the OpenAI key
  in the frontend.
- **The two services need each other's public URL.** The frontend must know the
  backend URL (`VITE_API_BASE_URL`); the backend must allow the frontend origin
  (`ALLOWED_ORIGINS`). We handle this with Railway "reference variables" so you
  don't copy-paste URLs by hand.

---

## 2. Accounts you need (and why)

You need **four** accounts. Three of them you already created in earlier phases.

| Account | New for Phase 9? | Why | Where |
| --- | --- | --- | --- |
| **GitHub** | No | Railway deploys by watching a branch in your repo. | github.com |
| **Supabase (production project)** | Recommended new project | Database + Auth for production. Keep it separate from your dev project. | supabase.com |
| **OpenAI** | No | Answers + embeddings. Make sure billing/quota is set. | platform.openai.com |
| **Railway** | **Yes** | Hosts the backend + frontend services. | railway.com |

> **Strongly recommended:** create a **separate Supabase project** for production
> rather than reusing your development one. It keeps test users, test chats, and
> schema experiments out of your real data. If you create a new project, you will
> run migrations and ingestion against it fresh (steps in the deployment guide).

### 2a. Create the Railway account

1. Go to [railway.com](https://railway.com/) and sign up **with GitHub** (this is
   what lets Railway see your repository).
2. Authorize Railway to access GitHub. You can scope it to just the
   `document-copilot` repo instead of all repos.
3. Check the plan/billing. Railway's free/trial usage is limited and typically
   sleeps or caps resource hours. For a pilot that 5 analysts use daily, expect
   to be on a paid plan (the **Hobby** plan is usually enough for a pilot). Set a
   spending alert if the dashboard offers one.

That's the entire Railway account setup. Everything else (projects, services,
domains) is configured per-deployment in the next guide.

---

## 3. Local tools you need

You almost certainly already have these from earlier phases. Verify:

```bash
python --version   # 3.12+
uv --version
node --version     # 20+ (the frontend Docker build uses Node 24)
pnpm --version
git --version
```

### Railway CLI (recommended)

You do **not** strictly need the CLI to deploy — the dashboard can do everything.
But you **do** need it to run database migrations and corpus ingestion against
production, because those run from your machine using Railway's production
variables. Install it:

```bash
# macOS / Linux (Homebrew)
brew install railway

# or via npm
npm i -g @railway/cli

# then log in
railway login
```

Verify:

```bash
railway whoami
```

### Docker (optional but handy)

The frontend deploys via a `Dockerfile`. Railway builds it in the cloud, so you
don't need Docker locally — but if you have it, you can catch build errors before
pushing. See the local build command in
[railway-deployment.md § 2](railway-deployment.md).

---

## 4. Repo readiness — what must already exist

The two services build in **different ways**, so each has its own committed
config. All of the following are already in the repo (added alongside this guide):

**Frontend — built from a Dockerfile (it's a static bundle that needs a server):**

- **`frontend/Dockerfile`** — builds the Vite bundle, then serves it with Caddy.
  Do **not** run `vite dev` in production.
- **`frontend/Caddyfile`** — serves the static bundle and, critically, contains
  the SPA fallback (`try_files {path} /index.html`) so refreshing a client-side
  route like `/sign-in` doesn't 404.

**Backend — built from its own Dockerfile (uv-based):**

- **`backend/Dockerfile`** — a `uv` image that installs the locked, production-only
  dependencies and starts production Uvicorn. A Dockerfile always takes precedence
  over Railway's default builder, so this is what Railway uses. See § 4a below.
- **`backend/.dockerignore`** — keeps the build context lean (caches, `.env`,
  tests, notebooks).
- **`backend/.python-version`** — pins Python `3.12` for local `uv`. The Docker
  base image already pins the same version for the deployed build.

Before you deploy, confirm all of these are committed and pushed:

```bash
git status              # frontend/Dockerfile, frontend/Caddyfile,
                        # backend/Dockerfile, backend/.dockerignore tracked
git log --oneline -1    # your deploy branch is pushed to GitHub
```

---

## 4a. How the backend actually deploys

The backend is built from `backend/Dockerfile`. **Railway always builds with a
Dockerfile when it finds one**, so it uses this instead of the default Railpack
builder — you don't set the builder anywhere. The image:

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# 1) install locked, production-only deps in a cached layer
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev
COPY . /app
# 2) install the app itself
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
# 3) production Uvicorn on Railway's injected $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Why it's built this way:

- **`--frozen --no-dev`** installs exactly what `uv.lock` pins, minus the `dev`
  group (docling, pytest, ruff, ipykernel). Those are only needed locally — e.g.
  corpus ingestion, which runs on *your* machine via `railway run`, not in this
  container — so excluding them keeps the image small.
- **Two `uv sync` steps** put dependencies in a separate Docker layer from your
  code, so editing `app/` doesn't re-download dependencies on every build.
- **`CMD` is production Uvicorn** bound to `0.0.0.0` and Railway's injected
  `$PORT`, with **no `--reload`** and no hardcoded `8000` (never use the
  `python app/main.py` dev entrypoint in production).
- Putting the venv on `PATH` means `uvicorn` and `alembic` run directly, without
  an `uv run` prefix.

**Migrations are NOT in the Dockerfile.** Never run `alembic upgrade head` at
image-build time — the build has no database and runs on every push. Instead set
it as Railway's **pre-deploy command** (a deploy-time setting), so it runs once
against the production database *before* the new container takes traffic and a
failed migration blocks that deploy. Because we're using a plain Dockerfile (no
`railway.json`), configure these in the `Backend` service dashboard:

| Dashboard setting | Value |
| --- | --- |
| Builder | Dockerfile (auto-detected from `backend/Dockerfile`) |
| Start Command | Leave empty — the Dockerfile `CMD` handles it |
| Pre-deploy Command | `alembic upgrade head` |
| Healthcheck Path | `/health` |
| Restart Policy | `On Failure` |

`GET /health` returns `{"status":"ok"}` once FastAPI is up; Railway gates the
deploy on it (it is not continuous uptime monitoring).

---

## 5. Preflight — prove it builds locally first

Never deploy something you haven't built locally. Run:

```bash
# Backend
cd backend
uv sync --locked
uv run pytest -m "not integration"
uv run ruff check .

# Frontend
cd ../frontend
pnpm install --frozen-lockfile
pnpm tsc --noEmit
pnpm lint
pnpm build
```

All of these must pass. `pnpm build` producing a `frontend/dist/` folder is your
proof the frontend Docker build will succeed.

If Docker is installed, you can also build the backend image locally to catch
build errors before pushing (it needs no env vars at build time):

```bash
docker build -t document-copilot-backend backend
```

---

## 6. Gather your secrets before touching Railway

Have these ready in a scratch file (never commit it). You will paste them into
Railway's **Variables** tab in the next guide. The right-hand column tells you
exactly where each value lives.

### Backend variables (secret — Backend service only)

| Variable | Where to find it |
| --- | --- |
| `SUPABASE_URL` | Supabase → Project Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | Supabase → Project Settings → API → `anon` `public` key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API → `service_role` **secret** |
| `DATABASE_URL` | Supabase → Project Settings → Database → Connection string (see note) |
| `OPENAI_API_KEY` | platform.openai.com → API keys |
| `ALLOWED_ORIGINS` | The frontend's public URL — set via a Railway reference (guide § 6) |

**`DATABASE_URL` — read this carefully.** Use the **direct connection**
(`db.<ref>.supabase.co:5432`) or the **session pooler**
(`<region>.pooler.supabase.com:5432`). Do **not** use the transaction pooler on
port `6543` — Alembic migrations will be rejected. URL-encode special characters
in the password. The app expects the `postgresql://…` form (it rewrites the
driver to `psycopg` automatically).

Optional backend variables (they have sane defaults; set them to make production
intent explicit): `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL`,
`OPENAI_EMBEDDING_DIMENSIONS`, `LOG_LEVEL=INFO`, `LOG_JSON=true`,
`LOGFIRE_ENVIRONMENT=production`. Full list in `backend/.env.example`.

### Frontend variables (public — Frontend service only)

| Variable | Value / source |
| --- | --- |
| `VITE_API_BASE_URL` | The backend's public URL — set via a Railway reference (guide § 6) |
| `VITE_SUPABASE_URL` | Same as `SUPABASE_URL` |
| `VITE_SUPABASE_ANON_KEY` | Same as `SUPABASE_ANON_KEY` |

> **Reminder:** these three are baked into the browser bundle at build time.
> Changing any of them requires a **fresh frontend deploy**. And never add the
> service-role key, database URL, or OpenAI key here — even without a `VITE_`
> prefix.

---

## 7. Ready-to-deploy checklist

When every box is ticked, move to [railway-deployment.md](railway-deployment.md)
and start at its § 3 ("Create the Railway project and services").

- [ ] Railway account created and connected to GitHub, plan/billing sorted.
- [ ] Railway CLI installed and `railway whoami` works.
- [ ] Production Supabase project exists; you know its URL, anon key,
      service-role key, and a port-5432 connection string.
- [ ] OpenAI key ready, with billing and a usage limit configured.
- [ ] `frontend/Dockerfile`, `frontend/Caddyfile`, `backend/Dockerfile`, and
      `backend/.dockerignore` are committed and pushed.
- [ ] You know to set the Backend pre-deploy command to `alembic upgrade head`
      and healthcheck path to `/health` in the dashboard (§ 4a).
- [ ] Deploy branch is pushed to GitHub; no `.env` or secret is committed.
- [ ] Preflight passed: backend tests + ruff, and `pnpm build` produced `dist/`.
- [ ] All secrets from § 6 are gathered in a scratch file.
- [ ] You have a Supabase backup if you are migrating an existing production DB.

---

## 8. What happens next (preview of the deployment guide)

So you know the shape of the work ahead, the deployment guide walks through:

1. Create an **empty** Railway project with two empty services named exactly
   `Backend` and `Frontend` (the names matter — reference variables use them).
2. Point each service at the repo, set root directories (`/backend`, `/frontend`),
   start commands, and generate public domains.
3. Add the variables from § 6 (using `${{Backend.RAILWAY_PUBLIC_DOMAIN}}` and
   `${{Frontend.RAILWAY_PUBLIC_DOMAIN}}` references so the two URLs wire up
   automatically).
4. Deploy the **backend first**, run `alembic upgrade head`, confirm `/health`
   returns `{"status":"ok"}`.
5. Deploy the **frontend**, confirm routes don't 404 on refresh.
6. Configure Supabase Auth for production (Site URL, redirect URLs, re-enable
   email confirmation, set up real SMTP).
7. **Ingest the corpus into production** from your local machine (the corpus is
   gitignored, so it isn't in the Railway build) using
   `railway run --service Backend …`.
8. Run the end-to-end test with a real work email.

---

## Related docs

| Doc | Purpose |
| --- | --- |
| [railway-deployment.md](railway-deployment.md) | The detailed click-by-click deployment steps |
| [supabase-setup.md](supabase-setup.md) | Creating the Supabase project (DB + Auth) |
| [backend-setup.md](backend-setup.md) | FastAPI + Alembic commands |
| [frontend-setup.md](frontend-setup.md) | Vite + React scaffold |
| [../client-brief.md](../client-brief.md) | Smoke-test questions for the E2E test |
