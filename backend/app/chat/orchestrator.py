from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import HTTPException, status
from pydantic_ai.exceptions import (
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import FunctionToolCallEvent, PartStartEvent
from pydantic_ai.tools import RunContext

from app.assistant.agent import document_agent, usage_limits
from app.assistant.deps import DocumentAgentDeps, RetrievalRegistry
from app.auth.dependencies import AuthenticatedUser
from app.chat.messages import (
    UIMessage,
    assistant_parts,
    build_citation_inserts,
    citation_payload,
    extract_text,
    latest_user_message,
    prior_messages,
    to_model_history,
    truncate_title,
)
from app.chat.streaming import (
    stream_error,
    stream_grounded_answer,
    stream_start,
    stream_status,
)
from app.config import settings
from app.database.chats import (
    DEFAULT_THREAD_TITLE,
    ThreadRow,
    get_thread_raw,
    insert_citations,
    insert_message,
    next_sequence,
    touch_thread,
)
from app.database.users import ensure_app_user
from app.grounding.validator import GroundingError, validate_grounded_answer
from app.retrieval.retriever import DocumentRetriever

_STATUS_POLL_TIMEOUT = 0.25

logger = structlog.get_logger(__name__)


async def require_owned_thread(thread_id: UUID, user_id: UUID) -> ThreadRow:
    thread = await get_thread_raw(thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )
    if thread.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to access this thread",
        )
    return thread


def _tool_args(args: str | dict[str, Any] | None) -> dict[str, Any]:
    if args is None:
        return {}
    if isinstance(args, dict):
        return args
    try:
        parsed = json.loads(args)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _status_for_tool_call(event: FunctionToolCallEvent) -> str:
    tool_name = event.part.tool_name
    args = _tool_args(event.part.args)

    if tool_name == "search_filings":
        ticker = args.get("ticker")
        if ticker:
            return f"Searching filings for {ticker}…"
        return "Searching filings…"
    if tool_name in ("read_chunk", "read_surrounding_chunks"):
        return "Reading filing passages…"
    return "Retrieving source documents…"


def _make_event_stream_handler(
    status_queue: asyncio.Queue[str],
) -> Any:
    drafting_sent = False

    async def handler(
        _ctx: RunContext[DocumentAgentDeps],
        events: AsyncIterator[Any],
    ) -> None:
        nonlocal drafting_sent
        async for event in events:
            if isinstance(event, FunctionToolCallEvent):
                await status_queue.put(_status_for_tool_call(event))
            elif (
                isinstance(event, PartStartEvent)
                and not drafting_sent
                and getattr(event.part, "part_kind", None) == "text"
            ):
                drafting_sent = True
                await status_queue.put("Drafting grounded answer…")

    return handler


async def _yield_status_updates(
    status_queue: asyncio.Queue[str],
    agent_task: asyncio.Task[Any],
) -> AsyncIterator[str]:
    while not agent_task.done():
        try:
            message = await asyncio.wait_for(
                status_queue.get(),
                timeout=_STATUS_POLL_TIMEOUT,
            )
        except TimeoutError:
            continue
        async for chunk in stream_status(message):
            yield chunk

    while not status_queue.empty():
        message = status_queue.get_nowait()
        async for chunk in stream_status(message):
            yield chunk


async def run_grounded_turn(
    user: AuthenticatedUser,
    thread_id: UUID,
    messages: list[UIMessage],
) -> AsyncIterator[str]:
    await ensure_app_user(user.id, user.email)
    thread = await require_owned_thread(thread_id, user.id)

    user_message = latest_user_message(messages)
    if user_message is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No user message in request",
        )

    user_text = extract_text(user_message).strip()
    if not user_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="User message is empty",
        )

    sequence = await next_sequence(thread_id)
    user_message_id = UUID(user_message.id) if _is_uuid(user_message.id) else uuid4()
    assistant_message_id = uuid4()

    structlog.contextvars.bind_contextvars(
        thread_id=str(thread_id),
        user_id=str(user.id),
        assistant_message_id=str(assistant_message_id),
    )
    logger.info("chat_turn_started")

    try:
        await insert_message(
            thread_id,
            role="user",
            content=user_text,
            parts=[part.model_dump() for part in user_message.parts],
            sequence=sequence,
            message_id=user_message_id,
        )

        registry = RetrievalRegistry()
        deps = DocumentAgentDeps(
            retriever=DocumentRetriever(),
            registry=registry,
        )
        history = to_model_history(prior_messages(messages, user_message))
        status_queue: asyncio.Queue[str] = asyncio.Queue()

        async for chunk in stream_start(str(assistant_message_id)):
            yield chunk
        async for chunk in stream_status("Analyzing your question…"):
            yield chunk

        agent_task = asyncio.create_task(
            document_agent.run(
                user_text,
                deps=deps,
                message_history=history,
                usage_limits=usage_limits(),
                model_settings={"temperature": settings.agent_temperature},
                metadata={
                    "thread_id": str(thread_id),
                    "user_id": str(user.id),
                },
                event_stream_handler=_make_event_stream_handler(status_queue),
            )
        )

        try:
            async for chunk in _yield_status_updates(status_queue, agent_task):
                yield chunk

            result = await agent_task
            grounded = result.output

            async for chunk in stream_status("Validating citations…"):
                yield chunk
            validate_grounded_answer(grounded, registry)
        except (GroundingError, UnexpectedModelBehavior):
            logger.warning("chat_turn_grounding_failed", exc_info=True)
            async for chunk in stream_error(
                "The assistant response failed citation validation. Please try again."
            ):
                yield chunk
            return
        except UsageLimitExceeded:
            logger.warning("chat_turn_usage_limit_exceeded", exc_info=True)
            async for chunk in stream_error(
                "The assistant run exceeded its tool or request limit. Please narrow the question."
            ):
                yield chunk
            return
        except ModelHTTPError:
            # logger.error("chat_turn_model_unavailable", exc_info=True)
            logger.exception("chat_turn_model_unavailable")
            async for chunk in stream_error(
                "The language model service is unavailable. Please try again shortly."
            ):
                yield chunk
            return

        for citation in grounded.citations:
            if citation.chunk_id not in registry.passages:
                passage = await deps.retriever.get_chunk(citation.chunk_id)
                if passage is not None:
                    registry.register(passage)

        citation_payloads = [
            citation_payload(citation, registry.passages[citation.chunk_id])
            for citation in grounded.citations
        ]

        async for chunk in stream_grounded_answer(
            str(assistant_message_id),
            grounded.answer,
            citation_payloads,
            include_start=False,
        ):
            yield chunk

        await insert_message(
            thread_id,
            role="assistant",
            content=grounded.answer,
            parts=assistant_parts(grounded.answer, citation_payloads),
            sequence=sequence + 1,
            message_id=assistant_message_id,
        )
        await insert_citations(
            assistant_message_id,
            build_citation_inserts(grounded, registry.passages),
        )

        title = thread.title
        if thread.title == DEFAULT_THREAD_TITLE and sequence == 1:
            title = truncate_title(user_text)

        await touch_thread(thread_id, title=title)
        logger.info(
            "chat_turn_completed",
            citation_count=len(grounded.citations),
            insufficient_evidence=grounded.insufficient_evidence,
        )
    finally:
        structlog.contextvars.clear_contextvars()


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True
