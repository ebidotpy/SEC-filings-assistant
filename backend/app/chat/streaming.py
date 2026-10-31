from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "x-vercel-ai-ui-message-stream": "v1",
}


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def stream_start(message_id: str) -> AsyncIterator[str]:
    yield _sse({"type": "start", "messageId": message_id})


async def stream_status(message: str) -> AsyncIterator[str]:
    yield _sse(
        {
            "type": "data-status",
            "id": str(uuid4()),
            "data": {"message": message},
        }
    )


async def stream_text_deltas(
    message_id: str,
    text: str,
    *,
    stream_delay: float = 0.0,
    include_start: bool = True,
) -> AsyncIterator[str]:
    text_block_id = str(uuid4())

    if include_start:
        yield _sse({"type": "start", "messageId": message_id})
    yield _sse({"type": "text-start", "id": text_block_id})

    words = text.split(" ")
    for index, word in enumerate(words):
        delta = word if index == 0 else f" {word}"
        yield _sse({"type": "text-delta", "id": text_block_id, "delta": delta})
        if stream_delay > 0:
            await asyncio.sleep(stream_delay)

    yield _sse({"type": "text-end", "id": text_block_id})


async def stream_citation_parts(
    citations: list[dict[str, object]],
) -> AsyncIterator[str]:
    if not citations:
        return

    part_id = str(uuid4())
    yield _sse(
        {
            "type": "data-citations",
            "id": part_id,
            "data": {"citations": citations},
        }
    )


async def stream_finish() -> AsyncIterator[str]:
    yield _sse({"type": "finish"})
    yield "data: [DONE]\n\n"


async def stream_error(error_text: str) -> AsyncIterator[str]:
    yield _sse({"type": "error", "errorText": error_text})
    yield _sse({"type": "finish"})
    yield "data: [DONE]\n\n"


async def stream_grounded_answer(
    message_id: str,
    answer_text: str,
    citations: list[dict[str, object]],
    *,
    include_start: bool = True,
) -> AsyncIterator[str]:
    async for chunk in stream_text_deltas(
        message_id,
        answer_text,
        include_start=include_start,
    ):
        yield chunk
    async for chunk in stream_citation_parts(citations):
        yield chunk
    async for chunk in stream_finish():
        yield chunk
