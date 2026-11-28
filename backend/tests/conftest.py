from __future__ import annotations

import json
import os
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI

# Pytest executes conftest.py before importing test modules. Providing a default
# mock API key ensures test collection and unit test execution succeed in CI
# or fresh checkouts where no local .env file exists.
os.environ.setdefault("OPENAI_API_KEY", "mock-openai-key-for-unit-tests")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def model_completion():
    def completion(**message):
        return {
            "id": "chat-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", **message},
                    "finish_reason": "tool_calls"
                    if message.get("tool_calls")
                    else "stop",
                }
            ],
        }

    return completion


@pytest.fixture
def model_tool_call():
    def tool_call(name, arguments, call_id="call-test"):
        return {
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments)
                if not isinstance(arguments, str)
                else arguments,
            },
        }

    return tool_call


@pytest.fixture
async def mock_openai():
    requests = []
    responses = []

    async def respond(request):
        requests.append(json.loads(request.content))
        response = responses.pop(0)
        return (
            response
            if isinstance(response, httpx.Response)
            else httpx.Response(200, json=response)
        )

    async with AsyncOpenAI(
        api_key="mock-openai-key",
        base_url="https://model.example.test/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    ) as client:
        yield SimpleNamespace(client=client, requests=requests, responses=responses)
