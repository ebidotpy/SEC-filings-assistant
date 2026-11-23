from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import FunctionToolCallEvent, ToolCallPart

from app.assistant.outputs import Citation, GroundedAnswer
from app.auth.dependencies import AuthenticatedUser
from app.chat.messages import UIMessage, UIMessagePart
from app.chat.orchestrator import run_grounded_turn
from app.database.chats import ThreadRow
from app.retrieval.types import SourcePassage

USER_ID = UUID("00000000-0000-0000-0000-000000000100")
THREAD_ID = UUID("00000000-0000-0000-0000-000000000200")
CHUNK_ID = UUID("00000000-0000-0000-0000-000000000001")


def _messages() -> list[UIMessage]:
    return [
        UIMessage(
            id=str(uuid4()),
            role="user",
            parts=[
                UIMessagePart(
                    type="text", text="How did Apple Services revenue change?"
                )
            ],
        )
    ]


def _result() -> MagicMock:
    return MagicMock(
        output=GroundedAnswer(
            answer="Services revenue increased over the period. [1]",
            citations=[
                Citation(
                    citation_index=1,
                    chunk_id=CHUNK_ID,
                    excerpt="Services revenue increased over the period.",
                )
            ],
        )
    )


def _register_passage(deps) -> None:
    deps.registry.register(
        SourcePassage(
            chunk_id=CHUNK_ID,
            document_id=uuid4(),
            chunk_index=0,
            text="Services revenue increased over the period.",
            ticker="AAPL",
            company_name="Apple Inc.",
            form="10-K",
            filing_date=date(2024, 10, 31),
            accession_number="0000320193-24-000123",
        )
    )


@pytest.fixture
def persistence():
    now = datetime(2024, 1, 1, tzinfo=UTC)
    thread = ThreadRow(
        id=THREAD_ID, user_id=USER_ID, title="New chat", created_at=now, updated_at=now
    )
    with (
        patch("app.chat.orchestrator.ensure_app_user", new=AsyncMock()),
        patch(
            "app.chat.orchestrator.require_owned_thread",
            new=AsyncMock(return_value=thread),
        ),
        patch(
            "app.chat.orchestrator.insert_message",
            new=AsyncMock(return_value=MagicMock(sequence=1)),
        ) as save,
        patch("app.chat.orchestrator.touch_thread", new=AsyncMock()) as touch,
    ):
        yield save, touch


@pytest.mark.anyio
async def test_run_grounded_turn_streams_and_persists_on_success(persistence):
    save, touch = persistence

    async def fake_run(*args, **kwargs):
        _register_passage(kwargs["deps"])
        return _result()

    with patch("app.chat.orchestrator.document_agent.run", side_effect=fake_run):
        chunks = []
        async for chunk in run_grounded_turn(
            AuthenticatedUser(USER_ID, "analyst@example.com"),
            THREAD_ID,
            _messages(),
        ):
            if "text-delta" in chunk or '"type":"finish"' in chunk:
                assert save.await_count == 2
                touch.assert_awaited_once()
            chunks.append(chunk)

    stream = "".join(chunks)
    assert stream.index("data-status") < stream.index("text-delta")
    assert "data-citations" in stream
    assert save.call_args.kwargs["sequence"] == 2
    assert save.call_args.kwargs["citations"][0].chunk_id == CHUNK_ID


@pytest.mark.anyio
async def test_run_grounded_turn_emits_status_before_answer(persistence):
    async def fake_run(*args, **kwargs):
        _register_passage(kwargs["deps"])

        async def events():
            yield FunctionToolCallEvent(
                part=ToolCallPart(
                    tool_name="search_filings",
                    args={"ticker": "AAPL", "query": "revenue"},
                )
            )

        await kwargs["event_stream_handler"](MagicMock(), events())
        return _result()

    with patch("app.chat.orchestrator.document_agent.run", side_effect=fake_run):
        stream = "".join(
            [
                chunk
                async for chunk in run_grounded_turn(
                    AuthenticatedUser(USER_ID, "analyst@example.com"),
                    THREAD_ID,
                    _messages(),
                )
            ]
        )
    assert "Searching filings for AAPL" in stream
    assert stream.index("data-status") < stream.index("text-delta")


@pytest.mark.anyio
async def test_run_grounded_turn_does_not_persist_assistant_on_grounding_failure(
    persistence,
):
    save, touch = persistence
    with patch(
        "app.chat.orchestrator.document_agent.run",
        new=AsyncMock(return_value=_result()),
    ):
        stream = "".join(
            [
                chunk
                async for chunk in run_grounded_turn(
                    AuthenticatedUser(USER_ID, "analyst@example.com"),
                    THREAD_ID,
                    _messages(),
                )
            ]
        )
    assert "failed citation validation" in stream
    assert save.await_count == 1
    touch.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        UnexpectedModelBehavior("Exceeded maximum retries"),
        ModelHTTPError(status_code=503, model_name="test-model", body={}),
    ],
)
async def test_run_grounded_turn_maps_model_errors_to_stream_errors(persistence, error):
    save, touch = persistence
    with patch(
        "app.chat.orchestrator.document_agent.run", new=AsyncMock(side_effect=error)
    ):
        stream = "".join(
            [
                chunk
                async for chunk in run_grounded_turn(
                    AuthenticatedUser(USER_ID, "analyst@example.com"),
                    THREAD_ID,
                    _messages(),
                )
            ]
        )
    assert '"type":"error"' in stream
    assert "[DONE]" in stream
    assert save.await_count == 1
    touch.assert_not_awaited()


@pytest.mark.anyio
async def test_disconnect_cancels_model_work(persistence):
    save, _ = persistence
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_run(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with patch("app.chat.orchestrator.document_agent.run", side_effect=fake_run):
        generator = run_grounded_turn(
            AuthenticatedUser(USER_ID, "analyst@example.com"),
            THREAD_ID,
            _messages(),
        )
        await anext(generator)
        await anext(generator)
        pending = asyncio.create_task(anext(generator))
        await asyncio.wait_for(started.wait(), timeout=1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await generator.aclose()
    assert cancelled.is_set()
    assert save.await_count == 1
