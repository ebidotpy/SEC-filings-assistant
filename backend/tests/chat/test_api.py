from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.database.chats import ThreadRow
from app.main import app


@pytest.fixture
def user(monkeypatch):
    user = AuthenticatedUser(uuid4(), "analyst@example.com")
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: user)
    monkeypatch.setattr("app.chat.orchestrator.ensure_app_user", AsyncMock())
    return user


@pytest.mark.anyio
@pytest.mark.parametrize("owned, expected", [(False, 403), (None, 404)])
async def test_stream_rejects_inaccessible_threads_before_http_200(
    monkeypatch, user, owned, expected
):
    now = datetime.now(UTC)
    thread = ThreadRow(uuid4(), user.id, "New chat", now, now)
    other_thread = replace(thread, user_id=uuid4()) if owned is False else None
    monkeypatch.setattr(
        "app.chat.orchestrator.get_thread_raw", AsyncMock(return_value=other_thread)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/chat/stream",
            json={
                "threadId": str(thread.id),
                "messages": [
                    {
                        "id": "user-message",
                        "role": "user",
                        "parts": [{"type": "text", "text": "Revenue?"}],
                    }
                ],
            },
        )
    assert response.status_code == expected
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "messages",
    [[], [{"id": "1", "role": "user", "parts": [{"type": "text", "text": "  "}]}]],
)
async def test_stream_rejects_empty_questions_before_http_200(
    monkeypatch, user, messages
):
    now = datetime.now(UTC)
    thread = ThreadRow(uuid4(), user.id, "New chat", now, now)
    monkeypatch.setattr(
        "app.chat.orchestrator.get_thread_raw", AsyncMock(return_value=thread)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/chat/stream", json={"threadId": str(thread.id), "messages": messages}
        )
    assert response.status_code == 422
