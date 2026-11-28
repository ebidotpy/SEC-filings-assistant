from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing
from uuid import UUID, uuid4

import logfire
import structlog
from fastapi import HTTPException, status
from langgraph.errors import GraphRecursionError
from openai import APIError, AsyncOpenAI

from app.assistant.agent import AgentLimitError, document_agent, graph_config
from app.assistant.deps import DocumentAgentDeps, RetrievalRegistry
from app.assistant.outputs import GroundedAnswer
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
        history = to_model_history(prior_messages(messages, user_message))

        async for chunk in stream_start(str(assistant_message_id)):
            yield chunk
        async for chunk in stream_status("Analyzing your question…"):
            yield chunk

        try:
            async with AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.base_url,
                max_retries=0,
            ) as client:
                deps = DocumentAgentDeps(
                    retriever=DocumentRetriever(), registry=registry, client=client
                )
                grounded: GroundedAnswer | None = None
                with logfire.span(
                    "document_agent", thread_id=str(thread_id), user_id=str(user.id)
                ):
                    async with aclosing(
                        document_agent.astream(
                            {
                                "messages": [
                                    *history,
                                    {"role": "user", "content": user_text},
                                ]
                            },
                            context=deps,
                            config=graph_config(
                                {"thread_id": str(thread_id), "user_id": str(user.id)}
                            ),
                            stream_mode=["custom", "values"],
                        )
                    ) as events:
                        async for mode, data in events:
                            if mode == "custom":
                                async for chunk in stream_status(data):
                                    yield chunk
                            elif mode == "values":
                                grounded = data.get("grounded_answer")

            if grounded is None:
                raise GroundingError("The graph completed without a grounded answer")
            validate_grounded_answer(grounded, registry)
        except GroundingError:
            logger.warning("chat_turn_grounding_failed", exc_info=True)
            async for chunk in stream_error(
                "The assistant response failed citation validation. Please try again."
            ):
                yield chunk
            return
        except (AgentLimitError, GraphRecursionError):
            logger.warning("chat_turn_usage_limit_exceeded", exc_info=True)
            async for chunk in stream_error(
                "The assistant run exceeded its tool or request limit. Please narrow the question."
            ):
                yield chunk
            return
        except APIError:
            logger.exception("chat_turn_model_unavailable")
            async for chunk in stream_error(
                "The language model service is unavailable. Please try again shortly."
            ):
                yield chunk
            return

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
