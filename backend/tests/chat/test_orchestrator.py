from __future__ import annotations

import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from app.assistant.outputs import Citation, GroundedAnswer
from app.auth.dependencies import AuthenticatedUser
from app.chat.messages import UIMessage, UIMessagePart
from app.chat.orchestrator import run_grounded_turn
from app.database.chats import ThreadRow
from app.grounding.validator import GroundingError
from app.retrieval.types import SourcePassage
from pydantic_ai.exceptions import UnexpectedModelBehavior

USER_ID = UUID("00000000-0000-0000-0000-000000000100")
THREAD_ID = UUID("00000000-0000-0000-0000-000000000200")
CHUNK_ID = UUID("00000000-0000-0000-0000-000000000001")


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(id=USER_ID, email="analyst@driftwood.test")


def _thread() -> ThreadRow:
    now = datetime(2024, 1, 1, tzinfo=datetime.now().astimezone().tzinfo)
    return ThreadRow(
        id=THREAD_ID,
        user_id=USER_ID,
        title="New chat",
        created_at=now,
        updated_at=now,
    )


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


def _grounded_answer() -> GroundedAnswer:
    return GroundedAnswer(
        answer="Services revenue increased over the period. [1]",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_ID,
                excerpt="Services revenue increased over the period.",
            )
        ],
    )


def _collect_stream(chunks: list[str]) -> str:
    return "".join(chunks)


@pytest.mark.anyio
async def test_run_grounded_turn_streams_and_persists_on_success():
    run_result = MagicMock()
    run_result.output = _grounded_answer()

    with (
        patch("app.chat.orchestrator.ensure_app_user", new=AsyncMock()),
        patch(
            "app.chat.orchestrator.require_owned_thread",
            new=AsyncMock(return_value=_thread()),
        ),
        patch("app.chat.orchestrator.next_sequence", new=AsyncMock(return_value=1)),
        patch(
            "app.chat.orchestrator.insert_message", new=AsyncMock()
        ) as insert_message,
        patch(
            "app.chat.orchestrator.insert_citations", new=AsyncMock()
        ) as insert_citations,
        patch("app.chat.orchestrator.touch_thread", new=AsyncMock()),
        patch(
            "app.chat.orchestrator.document_agent.run",
            new=AsyncMock(return_value=run_result),
        ),
        patch(
            "app.chat.orchestrator.validate_grounded_answer",
            side_effect=lambda answer, reg: None,
        ),
        patch("app.chat.orchestrator.DocumentRetriever") as retriever_cls,
    ):
        retriever = AsyncMock()
        retriever.get_chunk = AsyncMock(
            return_value=SourcePassage(
                chunk_id=CHUNK_ID,
                document_id=UUID("00000000-0000-0000-0000-000000000010"),
                chunk_index=0,
                text="Services revenue increased over the period.",
                ticker="AAPL",
                company_name="Apple Inc.",
                form="10-K",
                filing_date=date(2024, 10, 31),
                accession_number="0000320193-24-000123",
            )
        )
        retriever_cls.return_value = retriever
        chunks: list[str] = []
        async for chunk in run_grounded_turn(
            _user(),
            THREAD_ID,
            _messages(),
        ):
            chunks.append(chunk)

    stream = _collect_stream(chunks)
    assert "data-status" in stream
    assert stream.index("data-status") < stream.index("text-delta")
    assert "text-delta" in stream
    assert "data-citations" in stream
    assert insert_message.await_count == 2
    insert_citations.assert_awaited_once()


@pytest.mark.anyio
async def test_run_grounded_turn_emits_status_before_answer():
    from pydantic_ai.messages import FunctionToolCallEvent, ToolCallPart

    run_result = MagicMock()
    run_result.output = _grounded_answer()

    async def fake_run(*args, **kwargs):
        handler = kwargs.get("event_stream_handler")
        if handler is not None:
            ctx = MagicMock()
            event = FunctionToolCallEvent(
                part=ToolCallPart(
                    tool_name="search_filings",
                    args={"ticker": "AAPL", "query": "revenue"},
                )
            )
            await handler(ctx, _async_iter([event]))
        await asyncio.sleep(0.05)
        return run_result

    with (
        patch("app.chat.orchestrator.ensure_app_user", new=AsyncMock()),
        patch(
            "app.chat.orchestrator.require_owned_thread",
            new=AsyncMock(return_value=_thread()),
        ),
        patch("app.chat.orchestrator.next_sequence", new=AsyncMock(return_value=1)),
        patch("app.chat.orchestrator.insert_message", new=AsyncMock()),
        patch("app.chat.orchestrator.insert_citations", new=AsyncMock()),
        patch("app.chat.orchestrator.touch_thread", new=AsyncMock()),
        patch(
            "app.chat.orchestrator.document_agent.run",
            side_effect=fake_run,
        ),
        patch(
            "app.chat.orchestrator.validate_grounded_answer",
            side_effect=lambda answer, reg: None,
        ),
        patch("app.chat.orchestrator.DocumentRetriever") as retriever_cls,
    ):
        retriever = AsyncMock()
        retriever.get_chunk = AsyncMock(
            return_value=SourcePassage(
                chunk_id=CHUNK_ID,
                document_id=UUID("00000000-0000-0000-0000-000000000010"),
                chunk_index=0,
                text="Services revenue increased over the period.",
                ticker="AAPL",
                company_name="Apple Inc.",
                form="10-K",
                filing_date=date(2024, 10, 31),
                accession_number="0000320193-24-000123",
            )
        )
        retriever_cls.return_value = retriever
        chunks: list[str] = []
        async for chunk in run_grounded_turn(
            _user(),
            THREAD_ID,
            _messages(),
        ):
            chunks.append(chunk)

    stream = _collect_stream(chunks)
    assert "Analyzing your question" in stream
    assert "Searching filings for AAPL" in stream
    assert stream.index("data-status") < stream.index("text-delta")


async def _async_iter(items):
    for item in items:
        yield item


@pytest.mark.anyio
async def test_run_grounded_turn_does_not_persist_assistant_on_grounding_failure():
    run_result = MagicMock()
    run_result.output = _grounded_answer()

    with (
        patch("app.chat.orchestrator.ensure_app_user", new=AsyncMock()),
        patch(
            "app.chat.orchestrator.require_owned_thread",
            new=AsyncMock(return_value=_thread()),
        ),
        patch("app.chat.orchestrator.next_sequence", new=AsyncMock(return_value=1)),
        patch(
            "app.chat.orchestrator.insert_message", new=AsyncMock()
        ) as insert_message,
        patch(
            "app.chat.orchestrator.insert_citations", new=AsyncMock()
        ) as insert_citations,
        patch(
            "app.chat.orchestrator.document_agent.run",
            new=AsyncMock(return_value=run_result),
        ),
        patch(
            "app.chat.orchestrator.validate_grounded_answer",
            side_effect=GroundingError("bad citations"),
        ),
    ):
        chunks: list[str] = []
        async for chunk in run_grounded_turn(
            _user(),
            THREAD_ID,
            _messages(),
        ):
            chunks.append(chunk)

    stream = _collect_stream(chunks)
    assert "error" in stream
    assert insert_message.await_count == 1
    insert_citations.assert_not_awaited()


@pytest.mark.anyio
async def test_run_grounded_turn_maps_retry_exhaustion_to_error():
    with (
        patch("app.chat.orchestrator.ensure_app_user", new=AsyncMock()),
        patch(
            "app.chat.orchestrator.require_owned_thread",
            new=AsyncMock(return_value=_thread()),
        ),
        patch("app.chat.orchestrator.next_sequence", new=AsyncMock(return_value=1)),
        patch(
            "app.chat.orchestrator.insert_message", new=AsyncMock()
        ) as insert_message,
        patch(
            "app.chat.orchestrator.insert_citations", new=AsyncMock()
        ) as insert_citations,
        patch(
            "app.chat.orchestrator.document_agent.run",
            new=AsyncMock(
                side_effect=UnexpectedModelBehavior("Exceeded maximum retries")
            ),
        ),
    ):
        chunks: list[str] = []
        async for chunk in run_grounded_turn(
            _user(),
            THREAD_ID,
            _messages(),
        ):
            chunks.append(chunk)

    stream = _collect_stream(chunks)
    assert "error" in stream
    assert insert_message.await_count == 1
    insert_citations.assert_not_awaited()
