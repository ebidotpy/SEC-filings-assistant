from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app import embeddings as app_embeddings
from ingest import embeddings
from openai import RateLimitError


def _rate_limit_error(retry_after: str | None = None) -> RateLimitError:
    response = SimpleNamespace(
        request=SimpleNamespace(),
        status_code=429,
        headers={"retry-after": retry_after} if retry_after else {},
    )
    return RateLimitError("rate limit", response=response, body=None)


def _embedding_response(values: list[list[float]]):
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=index, embedding=embedding)
            for index, embedding in enumerate(values)
        ]
    )


@pytest.mark.anyio
async def test_create_embeddings_with_retry_on_rate_limit():
    create = AsyncMock(
        side_effect=[
            _rate_limit_error("1"),
            _embedding_response([[0.1, 0.2]]),
        ]
    )
    client = AsyncMock()

    with (
        patch.object(app_embeddings, "_create_embeddings", create),
        patch.object(app_embeddings.asyncio, "sleep", new=AsyncMock()),
    ):
        response = await embeddings.create_embeddings_with_retry(client, ["hello"])

    assert response.data[0].embedding == [0.1, 0.2]
    assert create.await_count == 2


@pytest.mark.anyio
async def test_create_embeddings_with_retry_raises_after_max_retries():
    create = AsyncMock(side_effect=_rate_limit_error())
    client = AsyncMock()

    with (
        patch.object(app_embeddings, "_create_embeddings", create),
        patch.object(app_embeddings.asyncio, "sleep", new=AsyncMock()),
        pytest.raises(RateLimitError),
    ):
        await embeddings.create_embeddings_with_retry(client, ["hello"])

    assert create.await_count == embeddings.MAX_RETRIES + 1
