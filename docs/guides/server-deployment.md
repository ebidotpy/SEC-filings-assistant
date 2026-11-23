# Server deployment

The current deployment entry point is `.github/workflows/deploy.yml` (the **Manual deploy** GitHub Actions workflow). It builds the frontend, backs up PostgreSQL, transfers the repository to the server, writes backend configuration, installs runtime dependencies, applies Alembic migrations, restarts Supervisor, reloads Nginx, and checks the public API health endpoint.

## Server prerequisites

Match the workflow's paths and database names to your server before running it:

- Application checkout: `/web_app/`, with the backend at `/web_app/backend`.
- Database Compose file: `/opt/postgres/compose.yaml`, with a service named `postgres`.
- PostgreSQL database: `sec-filings-assistant`. The backup runs `pg_dump` and `pg_restore` as the `postgres` user.
- Backup directory: `/var/backups/postgresql`; the workflow retains the five most recent verified dumps.
- uv installed in the deployment user's `$HOME/.local/bin`.
- Supervisor configured to run the backend from `/web_app/backend/.venv` and the deployment user permitted to restart it with `sudo supervisorctl`.
- Nginx configured to serve `/web_app/frontend/dist`, fall back to `index.html` for SPA routes, and proxy `/api/` to the backend without stripping `/api`. Disable proxy buffering for server-sent events. Permit the deployment user to test and reload Nginx.

The workflow currently restarts all Supervisor programs. Review that scope if the server runs additional applications.

## GitHub configuration

Configure these repository or `production` environment secrets:

| Secret | Purpose |
| --- | --- |
| `HOST_IP` | Server SSH host |
| `USERNAME` | Deployment SSH user |
| `SSH_KEY` | Deployment SSH private key |
| `DATABASE_URL` | Backend PostgreSQL connection URL with credentials |
| `POSTGRES_PASSWORD` | Password written to the server's backend configuration |
| `JWT_SECRET_KEY` | Random signing secret of at least 32 characters; preserve it across deployments |
| `OPENAI_API_KEY` | Key for the configured model provider |

The workflow currently configures `BASE_URL=https://api.avalai.ir/v1` and the listed chat and embedding models. Verify those choices against your provider. Frontend builds use `VITE_API_BASE_URL=/api`, so Nginx must proxy that path on the same origin. `ALLOWED_ORIGINS` matters if the frontend calls the backend across origins.

## Run and verify

Run **Manual deploy** from the intended branch and enter the public API health URL, for example `https://your-domain/api/health`. This checks the public proxy and backend regardless of whether Supervisor binds the backend to a TCP port or a Unix socket.

Deployments are serialized to prevent two runs from modifying the same installation concurrently. Rsync preserves server `.env` files, the backend virtual environment and its backup, and local caches. Dependency-installation failures restore the previous virtual environment. This rollback covers dependency installation; it does not roll back transferred source files or migrations.

After a successful deployment:

1. Open the app and confirm that registration and sign-in work.
2. Ask a question about an ingested filing and inspect its citations.
3. Reload the conversation and confirm that the answer and citations are still present.
4. Confirm that the database backup exists and check application logs for errors.

The health endpoint verifies application responsiveness. Checking sign-in and a sourced answer also verifies the database, retrieval, and model provider.
