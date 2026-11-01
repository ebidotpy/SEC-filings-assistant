from __future__ import annotations

import os

# Pytest executes conftest.py before importing test modules. Providing a default
# mock API key ensures test collection and unit test execution succeed in CI
# or fresh checkouts where no local .env file exists.
os.environ.setdefault("OPENAI_API_KEY", "mock-openai-key-for-unit-tests")
