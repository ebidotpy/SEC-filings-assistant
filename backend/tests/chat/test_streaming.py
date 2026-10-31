from __future__ import annotations

import json

import pytest
from app.chat.streaming import stream_start, stream_status, stream_text_deltas


def _parse_sse_payloads(chunks: list[str]) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                payloads.append(json.loads(line.removeprefix("data: ")))
    return payloads


@pytest.mark.anyio
async def test_stream_start_emits_message_id():
    chunks: list[str] = []
    async for chunk in stream_start("msg-123"):
        chunks.append(chunk)

    payloads = _parse_sse_payloads(chunks)
    assert payloads == [{"type": "start", "messageId": "msg-123"}]


@pytest.mark.anyio
async def test_stream_status_emits_data_status_part():
    chunks: list[str] = []
    async for chunk in stream_status("Searching filings for AAPL…"):
        chunks.append(chunk)

    payloads = _parse_sse_payloads(chunks)
    assert len(payloads) == 1
    assert payloads[0]["type"] == "data-status"
    assert payloads[0]["data"] == {"message": "Searching filings for AAPL…"}
    assert isinstance(payloads[0]["id"], str)


@pytest.mark.anyio
async def test_stream_text_deltas_can_skip_start():
    chunks: list[str] = []
    async for chunk in stream_text_deltas(
        "msg-123", "hello world", include_start=False
    ):
        chunks.append(chunk)

    payloads = _parse_sse_payloads(chunks)
    types = [payload["type"] for payload in payloads]
    assert "start" not in types
    assert types[0] == "text-start"
    assert any(payload["type"] == "text-delta" for payload in payloads)
