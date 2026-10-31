# syntax=docker/dockerfile:1

# Railway builds the backend from this Dockerfile: a Dockerfile always takes
# precedence over the default Railpack builder. Base image ships Python 3.12 and
# uv, so no interpreter or uv install step is needed.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# - Compile bytecode for faster cold starts.
# - Copy packages into the venv instead of hardlinking.
# - Never fetch a managed Python; use the interpreter in this base image.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime dependencies in their own layer so app-code edits don't
# invalidate the dependency cache. --no-dev excludes docling/pytest/ruff/ipykernel,
# which are only needed locally (e.g. corpus ingestion run via `railway run`).
RUN --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY . /app

# Install the project itself against the locked, prod-only environment.
RUN uv sync --frozen --no-dev

# Put the venv on PATH so `uvicorn` and `alembic` run without an `uv run` prefix.
ENV PATH="/app/.venv/bin:$PATH"

# Railway injects $PORT at runtime; default to 8000 for a local `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
