from __future__ import annotations

import os

import pytest

# Pytest executes conftest.py before importing test modules. Providing a default
# mock API key ensures test collection and unit test execution succeed in CI
# or fresh checkouts where no local .env file exists.
os.environ.setdefault("OPENAI_API_KEY", "mock-openai-key-for-unit-tests")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5434/unit_tests"
)
os.environ.setdefault(
    "JWT_SECRET_KEY", "unit-test-secret-key-with-at-least-32-characters"
)


@pytest.fixture
def anyio_backend():
    # Request orchestration uses asyncio tasks, queues, and cancellation.
    return "asyncio"
