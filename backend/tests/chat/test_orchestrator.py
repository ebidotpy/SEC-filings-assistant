from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
import pytest

from app.auth.dependencies import AuthenticatedUser
from app.chat.messages import UIMessage, UIMessagePart
from app.chat.orchestrator import run_grounded_turn
from app.config import settings
from app.database.chats import ThreadRow
from app.retrieval.types import SourcePassage

USER_ID = UUID("00000000-0000-0000-0000-000000000100")
THREAD_ID = UUID("00000000-0000-0000-0000-000000000200")
CHUNK_ID = UUID("00000000-0000-0000-0000-000000000001")


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(id=USER_ID, email="analyst@driftwood.test")


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


def _answer() -> dict:
    return {
        "answer": "Services revenue increased over the period. [1]",
        "citations": [
            {
                "citation_index": 1,
                "chunk_id": str(CHUNK_ID),
                "excerpt": "Services revenue increased over the period.",
            }
        ],
        "insufficient_evidence": False,
    }


@pytest.fixture
def turn_services(mock_openai):
    now = datetime(2024, 1, 1, tzinfo=UTC)
    thread = ThreadRow(
        id=THREAD_ID, user_id=USER_ID, title="New chat", created_at=now, updated_at=now
    )
    retriever = AsyncMock()
    retriever.search.return_value = [
        SourcePassage(
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
    ]
    with (
        patch("app.chat.orchestrator.ensure_app_user", new=AsyncMock()),
        patch(
            "app.chat.orchestrator.require_owned_thread",
            new=AsyncMock(return_value=thread),
        ),
        patch("app.chat.orchestrator.next_sequence", new=AsyncMock(return_value=1)),
        patch("app.chat.orchestrator.insert_message", new=AsyncMock()) as messages,
        patch("app.chat.orchestrator.insert_citations", new=AsyncMock()) as citations,
        patch("app.chat.orchestrator.touch_thread", new=AsyncMock()) as touch,
        patch("app.chat.orchestrator.DocumentRetriever", return_value=retriever),
        patch("app.chat.orchestrator.AsyncOpenAI", return_value=mock_openai.client),
    ):
        yield SimpleNamespace(
            retriever=retriever, messages=messages, citations=citations, touch=touch
        )


@pytest.mark.anyio
async def test_run_grounded_turn_streams_and_persists_on_success(
    turn_services, mock_openai, model_completion, model_tool_call
):
    mock_openai.responses.extend(
        [
            model_completion(
                tool_calls=[
                    model_tool_call(
                        "search_filings",
                        {"query": "Services revenue", "ticker": "AAPL"},
                    )
                ]
            ),
            model_completion(tool_calls=[model_tool_call("submit_answer", _answer())]),
        ]
    )

    stream = "".join(
        [chunk async for chunk in run_grounded_turn(_user(), THREAD_ID, _messages())]
    )

    assert stream.index("Searching filings for AAPL") < stream.index("text-delta")
    assert stream.index("Validating citations") < stream.index("text-delta")
    assert "data-citations" in stream
    assert "[DONE]" in stream
    assert turn_services.messages.await_count == 2
    assert turn_services.messages.await_args.kwargs["content"] == _answer()["answer"]
    turn_services.citations.assert_awaited_once()
    assert turn_services.citations.await_args.args[1][0].chunk_id == CHUNK_ID
    turn_services.touch.assert_awaited_once()
    assert mock_openai.client.is_closed()


@pytest.mark.anyio
async def test_run_grounded_turn_passes_conversation_history(
    turn_services, mock_openai, model_completion, model_tool_call
):
    mock_openai.responses.append(
        model_completion(
            tool_calls=[
                model_tool_call(
                    "submit_answer",
                    {
                        "answer": "Please specify a filing year.",
                        "citations": [],
                        "insufficient_evidence": True,
                    },
                )
            ]
        )
    )
    messages = [
        UIMessage(
            id=str(uuid4()),
            role="user",
            parts=[UIMessagePart(type="text", text="Let's discuss Apple.")],
        ),
        UIMessage(
            id=str(uuid4()),
            role="assistant",
            parts=[UIMessagePart(type="text", text="Which year?")],
        ),
        *_messages(),
    ]

    stream = "".join(
        [chunk async for chunk in run_grounded_turn(_user(), THREAD_ID, messages)]
    )

    assert mock_openai.requests[0]["messages"][1:] == [
        {"role": "user", "content": "Let's discuss Apple."},
        {"role": "assistant", "content": "Which year?"},
        {"role": "user", "content": "How did Apple Services revenue change?"},
    ]
    assert "text-delta" in stream
    assert "data-citations" not in stream
    assert turn_services.messages.await_count == 2


@pytest.mark.anyio
async def test_run_grounded_turn_does_not_persist_assistant_on_grounding_failure(
    turn_services, mock_openai, model_completion, model_tool_call
):
    mock_openai.responses.extend(
        [
            model_completion(tool_calls=[model_tool_call("submit_answer", _answer())])
            for _ in range(settings.agent_output_retries + 1)
        ]
    )

    stream = "".join(
        [chunk async for chunk in run_grounded_turn(_user(), THREAD_ID, _messages())]
    )

    assert "failed citation validation" in stream
    assert "text-delta" not in stream
    assert turn_services.messages.await_count == 1
    turn_services.citations.assert_not_awaited()
    turn_services.touch.assert_not_awaited()
    assert mock_openai.client.is_closed()


@pytest.mark.anyio
async def test_run_grounded_turn_maps_request_limit_to_error(
    turn_services, mock_openai, model_completion, model_tool_call, monkeypatch
):
    monkeypatch.setattr(settings, "agent_max_requests", 1)
    mock_openai.responses.append(
        model_completion(
            tool_calls=[model_tool_call("search_filings", {"query": "revenue"})]
        )
    )

    stream = "".join(
        [chunk async for chunk in run_grounded_turn(_user(), THREAD_ID, _messages())]
    )

    assert "exceeded its tool or request limit" in stream
    assert "text-delta" not in stream
    assert turn_services.messages.await_count == 1
    turn_services.citations.assert_not_awaited()


@pytest.mark.anyio
async def test_run_grounded_turn_maps_model_error_to_stream_error(
    turn_services, mock_openai
):
    mock_openai.responses.append(
        httpx.Response(503, json={"error": {"message": "model unavailable"}})
    )

    stream = "".join(
        [chunk async for chunk in run_grounded_turn(_user(), THREAD_ID, _messages())]
    )

    assert "language model service is unavailable" in stream
    assert "text-delta" not in stream
    assert "[DONE]" in stream
    assert turn_services.messages.await_count == 1
    turn_services.citations.assert_not_awaited()
    assert mock_openai.client.is_closed()


@pytest.mark.anyio
async def test_cancelled_turn_closes_graph_and_client(
    turn_services, mock_openai, model_completion, model_tool_call
):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def search(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    turn_services.retriever.search.side_effect = search
    mock_openai.responses.append(
        model_completion(
            tool_calls=[model_tool_call("search_filings", {"query": "revenue"})]
        )
    )

    async def consume():
        async for _ in run_grounded_turn(_user(), THREAD_ID, _messages()):
            pass

    task = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert cancelled.is_set()
    assert mock_openai.client.is_closed()
    assert turn_services.messages.await_count == 1
    turn_services.citations.assert_not_awaited()
