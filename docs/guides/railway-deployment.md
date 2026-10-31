# Railway production deployment

This guide deploys Document Copilot as two Railway services from the same GitHub
repository:

- **Backend** — FastAPI/Uvicorn from `/backend`
- **Frontend** — the Vite/React build from `/frontend`, served by Caddy
- **Database and Auth** — the existing hosted Supabase project
- **LLM and embeddings** — OpenAI

Railway should not host another Postgres service for this application. Supabase
remains the database and authentication provider.

> New to Railway? Start with [railway-setup.md](railway-setup.md) for the
> from-zero prerequisites (accounts, CLI, secret-gathering), then return here for
> the click-by-click deployment.

## What you need before starting

- A [Railway account](https://railway.com/) with GitHub connected and billing
  configured if your selected plan requires it.
- A GitHub repository that contains the branch you intend to deploy. Push all
  deployment-ready changes before connecting it to Railway.
- A production Supabase project. Using a separate project from local development
  is strongly recommended.
- The production Supabase project URL, anon key, service-role key, and a direct
  or session-pooler Postgres connection string.
- An OpenAI API key with billing and sufficient quota.
- The corpus downloaded and converted under `data/Markdown/` on the machine from
  which ingestion will run. These files are intentionally gitignored and will
  not exist in Railway builds.
- Python 3.12+, `uv`, Node.js, and `pnpm` installed locally for final checks.
- Optional: the [Railway CLI](https://docs.railway.com/cli) for running migrations
  and ingestion locally with Railway's production variables.

Never put the Supabase service-role key, database URL, or OpenAI key in the
frontend service. Every `VITE_*` value is embedded in browser JavaScript and is
public.

## Deployment order

Use this order because the two public domains are needed when configuring CORS
and the frontend API URL:

1. Run local preflight checks.
2. Add the frontend production-serving files.
3. Create an empty Railway project with empty `Backend` and `Frontend` services.
4. Configure both services and generate their public domains.
5. Add backend and frontend variables.
6. Deploy the backend, run migrations, and verify `/health`.
7. Deploy the frontend and verify SPA routing.
8. Configure Supabase production Auth.
9. Ingest the corpus into production.
10. Run the end-to-end checklist.

## 1. Preflight checks

Run these before deploying:

```bash
cd backend
uv sync --locked
uv run pytest -m "not integration"
uv run ruff check .

cd ../frontend
pnpm install --frozen-lockfile
pnpm tsc --noEmit
pnpm lint
pnpm build
```

Also confirm:

- The deployment branch is pushed to GitHub.
- No `.env` file or secret is committed.
- Production Supabase has a known database password.
- OpenAI billing and usage limits are appropriate.
- `backend/alembic/versions/` contains every migration intended for production.
- You have a current Supabase backup before applying migrations to an existing
  production database.

## 2. Prepare the frontend production server

The current frontend has a Vite build command but no production server. Do not
use `vite dev` in production. Add the following two files to `frontend/` before
the first Railway deployment.

### `frontend/Dockerfile`

```dockerfile
FROM node:24-alpine AS build

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@11.9.0 --activate

COPY package.json pnpm-lock.yaml .npmrc ./
RUN pnpm install --frozen-lockfile

COPY . .

# Railway exposes service variables as Docker build arguments. These values are
# intentionally public because Vite embeds them in the browser bundle.
ARG VITE_API_BASE_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

RUN pnpm build

FROM caddy:2-alpine

WORKDIR /app
COPY Caddyfile ./
RUN caddy fmt Caddyfile --overwrite
COPY --from=build /app/dist ./dist

CMD ["caddy", "run", "--config", "Caddyfile", "--adapter", "caddyfile"]
```

If the repository later pins another pnpm version in `package.json`, keep the
Dockerfile version in sync.

### `frontend/Caddyfile`

```caddy
{
    admin off
    persist_config off
    auto_https off
    log {
        format json
    }
    servers {
        trusted_proxies static private_ranges 100.0.0.0/8
    }
}

:{$PORT:3000} {
    log {
        format json
    }

    rewrite /health /*
    root * dist
    encode gzip
    try_files {path} /index.html
    file_server
}
```

The `try_files` fallback is required for React Router. Without it, opening or
refreshing a client-side route such as `/sign-in` returns a 404. Caddy listens
on Railway's injected `PORT`; do not hardcode or create a `PORT` variable.

Build the image locally if Docker is available:

```bash
docker build \
  --build-arg VITE_API_BASE_URL=http://localhost:8000 \
  --build-arg VITE_SUPABASE_URL=https://your-project-ref.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=your-anon-key \
  -t document-copilot-frontend \
  frontend
```

## 3. Create the Railway project and services

The repository is an isolated monorepo. Each application needs its own Railway
service and root directory.

1. Open the [Railway dashboard](https://railway.com/dashboard).
2. Select **New Project** → **Empty Project**.
3. Name it `Document Copilot`.
4. Add two empty services.
5. Name them exactly `Backend` and `Frontend`. These names are used by Railway
   reference variables later in this guide.
6. In each service, open **Settings** → **Source** and connect the same GitHub
   repository and production branch.
7. Turn on automatic deploys only if every push to that branch should deploy to
   production.

Creating empty services first avoids triggering incomplete deployments before
root directories, commands, domains, and variables are configured.

## 4. Configure the Backend service

The backend is built from `backend/Dockerfile`. Railway always builds with a
Dockerfile when it finds one, so there is no builder to select and no build
command to set. The Dockerfile installs the locked, production-only dependencies
(`uv sync --frozen --no-dev`) and its `CMD` runs production Uvicorn on `$PORT`.

In the `Backend` service settings, use:

| Setting | Value |
| --- | --- |
| Root Directory | `/backend` |
| Builder | Dockerfile (auto-detected from `backend/Dockerfile`) |
| Build Command | Leave empty; the Dockerfile builds the image |
| Start Command | Leave empty; the Dockerfile `CMD` starts Uvicorn |
| Pre-deploy Command | `alembic upgrade head` |
| Healthcheck Path | `/health` |
| Restart Policy | `On Failure` |
| Watch Path | `/backend/**` |

Important:

- Migrations are **not** run in the Dockerfile — the build has no database and
  runs on every push. The pre-deploy command applies Alembic migrations once,
  against production, before new application code receives traffic. A migration
  failure stops that deployment.
- Do not run `python app/main.py` in production. That path enables reload and
  hardcodes port 8000. The Dockerfile `CMD` binds `0.0.0.0` and `$PORT` instead.
- Keep one backend replica while migrations are first being established.
- `/health` returns HTTP 200 when FastAPI starts. Railway health checks gate a
  deployment; they are not continuous uptime monitoring.
- The `dev` dependency group (docling, pytest, ruff) is excluded from the image.
  It is only needed locally for corpus ingestion via `railway run`.

Under **Settings** → **Networking**, select **Generate Domain**. Record the
hostname, for example:

```text
document-copilot-backend-production.up.railway.app
```

Your backend URL is the hostname with `https://`:

```text
https://document-copilot-backend-production.up.railway.app
```

## 5. Configure the Frontend service

In the `Frontend` service settings, use:

| Setting | Value |
| --- | --- |
| Root Directory | `/frontend` |
| Builder | Dockerfile |
| Dockerfile Path | `Dockerfile` |
| Build Command | Leave empty; the Dockerfile runs `pnpm build` |
| Start Command | Leave empty; the Dockerfile starts Caddy |
| Healthcheck Path | `/health` |
| Restart Policy | `On Failure` |
| Watch Path | `/frontend/**` |

Under **Settings** → **Networking**, select **Generate Domain** and record the
hostname. Your user-facing application URL is that hostname with `https://`.

No persistent volume is needed for either service. Application state is in
Supabase and both containers should remain disposable.

## 6. Configure production variables

Railway variables are case-sensitive. Add them under the **Variables** tab of
the correct service.

### Backend required variables

| Variable | Value |
| --- | --- |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role secret |
| `DATABASE_URL` | Direct or session-pooler URL on port 5432 |
| `OPENAI_API_KEY` | Production OpenAI secret key |
| `ALLOWED_ORIGINS` | `https://${{Frontend.RAILWAY_PUBLIC_DOMAIN}}` |

`ALLOWED_ORIGINS` must contain browser origins, including the scheme and without
a trailing slash. For multiple exact origins, use a comma-separated value:

```text
https://${{Frontend.RAILWAY_PUBLIC_DOMAIN}},https://app.example.com
```

Do not use `*` because the API accepts authenticated browser requests and CORS
credentials are enabled.

`DATABASE_URL` must be one of:

- Supabase direct connection: `db.<project-ref>.supabase.co:5432`
- Supabase session pooler: `<region>.pooler.supabase.com:5432`

Do not use the transaction pooler on port `6543` for Alembic. URL-encode special
characters in the database password.

### Backend recommended production variables

These have application defaults, but setting them explicitly makes production
intent clear:

```text
OPENAI_CHAT_MODEL=gpt-5-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
OPENAI_EMBEDDING_MAX_CHUNK_TOKENS=512
LOG_LEVEL=INFO
LOG_JSON=true
LOGFIRE_ENVIRONMENT=production
```

If Logfire is used, also add its write token only to the backend:

```text
LOGFIRE_TOKEN=<production-write-token>
LOGFIRE_SERVICE_NAME=document-copilot-agent
```

The agent and retrieval tuning variables from `backend/.env.example` are
optional; their defaults come from `backend/app/config.py`.

### Frontend required variables

| Variable | Value |
| --- | --- |
| `VITE_API_BASE_URL` | `https://${{Backend.RAILWAY_PUBLIC_DOMAIN}}` |
| `VITE_SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon/public key |

Do not add `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, or `OPENAI_API_KEY` to
the frontend, even without a `VITE_` prefix.

Vite variables are embedded at build time. Any change to a `VITE_*` variable
requires a fresh frontend build and deployment. Do not enable Railway's skipped
build optimization for this service because a cached image can retain old
build-time values.

## 7. Deploy and migrate

Review all staged Railway changes, then deploy the backend first.

Watch the backend build and deployment logs. The sequence should be:

1. Dependencies install successfully from `uv.lock`.
2. `uv run alembic upgrade head` completes.
3. Uvicorn starts on `0.0.0.0:$PORT`.
4. Railway receives HTTP 200 from `/health`.

Verify from your terminal:

```bash
curl --fail --show-error \
  "https://<backend-domain>/health"
```

Expected response:

```json
{"status":"ok"}
```

To inspect migration state using the production backend variables:

```bash
cd backend
railway login
railway link
railway run --service Backend uv run alembic current
```

If the pre-deploy command was not configured, apply the migration explicitly:

```bash
railway run --service Backend uv run alembic upgrade head
```

Do not run schema changes manually in the Supabase SQL editor. Alembic is the
schema source of truth.

After the backend is healthy, deploy the frontend. Verify:

```bash
curl --fail --show-error --location \
  "https://<frontend-domain>/health"
```

Then open all of these directly in a browser:

- `https://<frontend-domain>/`
- `https://<frontend-domain>/sign-in`
- `https://<frontend-domain>/sign-up`

Refresh each route. A 404 on refresh means the Caddy SPA fallback is missing or
the frontend was not built from the expected Dockerfile.

## 8. Configure Supabase Auth for production

In Supabase:

1. Open **Authentication** → **URL Configuration**.
2. Set **Site URL** to the exact frontend origin:

   ```text
   https://<frontend-domain>
   ```

3. Add the frontend URL to **Redirect URLs**. If supported by the dashboard,
   add `https://<frontend-domain>/**` so future auth callback routes are allowed.
4. Open **Authentication** → **Providers** → **Email**.
5. Enable email/password sign-up.
6. Re-enable **Confirm email** if it was disabled for local development.
7. Test the confirmation link with a real email inbox.

The current signup call does not pass a custom `emailRedirectTo`, so confirmed
users are redirected to Supabase's configured Site URL. An incorrect Site URL
will send production users to localhost or another environment.

Supabase's built-in email sender is intended for testing and is heavily rate
limited. Configure a custom SMTP provider under the Supabase Auth email settings
before relying on confirmation email in production. Verify sender-domain DNS,
delivery, spam placement, and rate limits.

## 9. Ingest the production corpus

The corpus files are gitignored, so ingestion should run from the local machine
that has `data/Markdown/`, while injecting the Railway backend's production
variables.

Confirm the linked Railway environment is `production`, then run from
`backend/`:

```bash
railway run --service Backend \
  uv run --group dev python ingest/load_source_documents.py

railway run --service Backend \
  uv run --group dev python ingest/load_document_chunks.py
```

Run source-document ingestion first. Chunk ingestion calls OpenAI embeddings and
can take time and incur API cost. The scripts skip existing records by default.
Do not use `--force` unless replacing existing production chunks is intentional.

Before a full chunk run, an optional local parser smoke test is:

```bash
railway run --service Backend \
  uv run --group dev python ingest/load_document_chunks.py \
  --dry-run --limit-chunks 5
```

The dry run validates local parsing only; it does not call OpenAI or write to the
database.

Verify production Supabase contains:

- rows in `source_documents`
- rows in `document_chunks`
- non-null embeddings
- generated search vectors
- chat and citation tables from Alembic
- enabled row-level security policies

## 10. End-to-end production test

Use a new Driftwood-style work email account and test the deployed URLs:

- [ ] Signup displays the confirmation-email message.
- [ ] Confirmation email arrives and its link returns to the production frontend.
- [ ] The confirmed user can sign in and sign out.
- [ ] Browser developer tools show no CORS errors.
- [ ] The frontend calls the HTTPS Railway backend, not localhost.
- [ ] An authenticated chat can be created.
- [ ] A representative question streams an answer rather than waiting for one
      final response.
- [ ] The answer contains valid citations.
- [ ] Citation/source details open successfully.
- [ ] Chat history survives sign-out/sign-in and a browser refresh.
- [ ] A second user cannot read the first user's chat history.
- [ ] Backend logs contain no secret values or full authorization headers.
- [ ] Railway build, deploy, and HTTP logs show no repeated failures.
- [ ] OpenAI usage and Supabase database usage appear under the expected
      production projects.

Suggested smoke-test questions are listed in `docs/client-brief.md`.

## Custom domains

Add custom domains only after both Railway-generated domains work.

When the frontend domain changes:

1. Update backend `ALLOWED_ORIGINS`.
2. Update Supabase Auth **Site URL** and **Redirect URLs**.
3. Redeploy the backend.
4. Re-test signup confirmation and CORS.

When the backend domain changes:

1. Update frontend `VITE_API_BASE_URL`.
2. Rebuild and redeploy the frontend because Vite embeds the value at build time.
3. Verify requests use the new backend URL.

Keep the Railway domains in CORS only if they should remain valid production
entry points.

## Rollback and operations

- Use Railway deployment logs first for build or startup failures.
- Roll back application code from the service's **Deployments** view.
- Treat database rollback separately. Rolling back a container does not reverse
  an Alembic migration.
- Prefer forward-fix migrations. Test destructive migrations on staging and take
  a Supabase backup first.
- Railway's `/health` check only gates new deployments. Add an external uptime
  check if continuous monitoring is required.
- Review Railway CPU, memory, network, and restart metrics after realistic chat
  requests.
- Set Railway and OpenAI spending alerts where available.
- Rotate any secret that is accidentally placed in git, logs, screenshots, or a
  `VITE_*` variable.

## Troubleshooting

### Backend deploy says no start command

The start command comes from the Dockerfile `CMD`, so leave the dashboard Start
Command empty. If Railway does not detect the Dockerfile, confirm the root
directory is `/backend` and that `backend/Dockerfile` is committed and pushed.

### Backend health check fails

Check that:

- The Dockerfile `CMD` binds Uvicorn to `0.0.0.0` and `$PORT` (no `--reload`).
- All five required backend secrets are present.
- Startup logs do not show configuration or import errors.
- Healthcheck Path is `/health`.
- The image built from `backend/Dockerfile` (not a stale Railpack build).

### Migration rejects the database URL

The application intentionally rejects the Supabase transaction pooler on port
6543 for online migrations. Replace it with the direct connection or session
pooler on port 5432.

### Frontend build reports a missing environment variable

Add all three required `VITE_*` variables to the Frontend service and redeploy.
Check that the Dockerfile declares matching `ARG` and `ENV` names before
`pnpm build`.

### Frontend loads but API calls fail

In browser developer tools, inspect the request URL and console:

- `VITE_API_BASE_URL` must include `https://`.
- Backend `ALLOWED_ORIGINS` must exactly match the frontend origin.
- Neither value should have a trailing slash.
- Redeploy the frontend after changing `VITE_API_BASE_URL`.
- Redeploy the backend after changing `ALLOWED_ORIGINS`.

### Direct frontend routes return 404

Railway is not serving the SPA fallback. Confirm the frontend uses the Caddyfile
from this guide and contains:

```caddy
try_files {path} /index.html
```

### Confirmation email points to localhost

Update the Supabase Auth Site URL to the production frontend URL. The current
signup flow uses that default redirect.

### Chat starts but returns no grounded answers

Confirm migrations and both ingestion scripts completed against the same
Supabase project configured in the Backend service. Check that
`document_chunks.embedding` contains data and that the OpenAI model names and
embedding dimensions match the migrated vector column.

## Official references

- [Railway: Deploying a monorepo](https://docs.railway.com/deployments/monorepo)
- [Railway: FastAPI](https://docs.railway.com/guides/fastapi)
- [Railway: React and Caddy](https://docs.railway.com/guides/react)
- [Railway: Frontend environment variables](https://docs.railway.com/guides/frontend-environment-variables)
- [Railway: Health checks](https://docs.railway.com/deployments/healthchecks)
- [Railway: Variables](https://docs.railway.com/reference/variables)
- [Supabase: Email Auth](https://supabase.com/docs/guides/auth/auth-email)
- [Supabase setup for this project](supabase-setup.md)
