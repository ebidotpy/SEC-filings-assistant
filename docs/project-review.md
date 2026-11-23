# Project review — November 23, 2026

Review branch: `codex/project-review`, created from `main` at `1d6471b`.

## Fixes

| Area | Problem found | Change |
| --- | --- | --- |
| Configuration | Missing database settings or JWT secrets silently used development defaults. | Require database URL, API key, and a JWT secret of at least 32 characters; reject known placeholder secrets. |
| Authentication | bcrypt rejects passwords over 72 UTF-8 bytes, producing server errors. Hashing also blocked the request event loop. | Validate registration passwords by byte length, safely reject oversized login passwords, and run bcrypt in a worker thread. |
| Registration | Concurrent registrations could both pass the email lookup and then produce an unhandled unique-constraint error. Oversized profile fields reached database writes. | Return a normal duplicate-email error and validate field lengths at the HTTP boundary. |
| Sessions | JWT decoding accepted signed tokens without expiration; profile names disappeared after restoring a session. | Require `sub`, `iat`, and `exp`; return the display name from `/auth/me`. |
| Chat API | Ownership and question validation ran after streaming headers had already sent HTTP 200. | Start the generator before constructing the streaming response so invalid requests receive 403, 404, or 422 JSON responses. |
| Chat persistence | Concurrent turns could allocate duplicate sequences. Answers finished streaming before they were saved, and citation saves used a separate transaction. | Allocate message pairs while holding a PostgreSQL row lock; save answers and citations together before streaming completion. Use server-generated message IDs. |
| Cancellation | Disconnecting left the independently created model task running. Navigating away also left the browser stream open. | Close the response generator, cancel and await model work, and stop browser streams on unmount while respecting React StrictMode. |
| Grounding | Whitespace-only excerpts normalized to an empty string, which matched every source passage. | Reject empty normalized excerpts and test spaces, tabs, and non-breaking spaces. |
| Ingestion | Committing each batch could leave a partial filing that future runs skipped. Forced ingestion deleted existing chunks before generating embeddings. | Generate embeddings first and commit all chunks, including replacement, in one transaction. |
| Migrations | Alembic loaded the declarative base without importing the table models. | Load populated model metadata for schema comparisons; preserve URLs correctly in offline SQL generation. |
| Frontend | History from the previous conversation could initialize the next conversation. Expired-session sign-in links retained the stale session, and validation errors showed only a generic status code. | Associate loaded history with its thread, clear session state immediately on sign-out, and display FastAPI validation messages. |
| Frontend loading | Sign-in loaded the entire chat implementation in one large JavaScript bundle. | Lazy-load the chat layout and thread page. The entry bundle decreased from 635.78 kB to 327.48 kB; gzip decreased from 186.49 kB to 106.13 kB. |
| CI and deployment | The deployed frontend build omitted its required API URL. Rsync could delete the virtual environment before rollback. Deployment omitted migrations and public health verification. | Build with `/api`, preserve server environments and caches, serialize deployments, apply migrations before restart, and check the supplied public health URL. Align CI Ruff with the locked version. |
| Documentation and containers | README instructions described Supabase authentication; frontend Docker builds copied host dependencies and exposed obsolete build inputs. | Document the current stack and server workflow, add frontend Docker exclusions, and remove obsolete Supabase build arguments. |

## Verification

- Backend unit suite: **80 passed, 8 integration tests deselected**. Exact versions from `backend/uv.lock` were loaded from the local uv cache after registry downloads failed. The suite includes HTTP access errors, worker-thread hashing, duplicate registrations, cancellation, grounding, and failed ingestion batches.
- Backend Ruff lint and formatting: passed.
- Frontend TypeScript and production build: passed. `pnpm build` runs the full TypeScript project build; the root `tsc --noEmit` command alone does not check the referenced application project.
- Frontend lint: passed with five existing Fast Refresh warnings. Changed frontend files pass Prettier checks.
- Browser: sign-in and registration navigation work locally; a clean reload showed no new console errors.
- Alembic: successfully generated SQL through the current migration head without connecting to a database.
- GitHub workflow YAML parsing and `git diff --check`: passed.

## Deployment details and remaining verification

The deployment workflow now asks for the public health URL, such as `https://your-domain/api/health`. Backend startup requires a non-placeholder JWT secret of at least 32 characters. Preserve the existing strong secret to keep issued tokens valid.

The server was reported down during this review. Live PostgreSQL transaction behavior, authenticated chat in the browser, reverse-proxy streaming, and the deployment workflow still need verification against a running environment. The unit tests verify service behavior with mocked database boundaries; offline migration generation does not apply migrations.

The existing workflow restarts all Supervisor programs and provides rollback for dependency installation only. Its server paths, database name, model provider, and Supervisor scope are documented in `docs/guides/server-deployment.md` for checking against the actual server.
