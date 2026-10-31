"""OpenAI embedding generation shared by ingestion and retrieval."""

from __future__ import annotations

import asyncio

import tiktoken
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from app.config import settings

OPENAI_EMBEDDING_MAX_INPUT_TOKENS = 8191
EMBED_BATCH_SIZE = 100
EMBED_INTER_BATCH_DELAY_SECONDS = 1.0
MAX_RETRIES = 6
INITIAL_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 60.0

RETRYABLE_ERRORS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)


def _encoding():
    return tiktoken.encoding_for_model(settings.openai_embedding_model)


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def validate_texts(texts: list[str]) -> None:
    for index, text in enumerate(texts):
        token_count = count_tokens(text)
        if token_count > OPENAI_EMBEDDING_MAX_INPUT_TOKENS:
            raise ValueError(
                f"Text at index {index} has {token_count} tokens "
                f"(max {OPENAI_EMBEDDING_MAX_INPUT_TOKENS})"
            )


def _retry_after_seconds(error: RateLimitError) -> float | None:
    if error.response is None:
        return None
    raw = error.response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def _create_embeddings(client: AsyncOpenAI, batch: list[str]):
    return await client.embeddings.create(
        input=batch,
        model=settings.openai_embedding_model,
        dimensions=settings.openai_embedding_dimensions,
    )


async def create_embeddings_with_retry(
    client: AsyncOpenAI,
    batch: list[str],
):
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(MAX_RETRIES + 1):
        try:
            return await _create_embeddings(client, batch)
        except RETRYABLE_ERRORS as error:
            if attempt >= MAX_RETRIES:
                raise

            if isinstance(error, RateLimitError):
                delay = _retry_after_seconds(error) or backoff
            else:
                delay = backoff

            delay = min(max(delay, INITIAL_BACKOFF_SECONDS), MAX_BACKOFF_SECONDS)
            print(
                f"Embedding request failed ({type(error).__name__}), "
                f"retry {attempt + 1}/{MAX_RETRIES} in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


def openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.base_url,
    )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    validate_texts(texts)

    client = openai_client()
    all_embeddings: list[list[float]] = []
    batch_starts = range(0, len(texts), EMBED_BATCH_SIZE)

    for batch_number, start in enumerate(batch_starts):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = await create_embeddings_with_retry(client, batch)
        ordered = sorted(response.data, key=lambda item: item.index)
        all_embeddings.extend(item.embedding for item in ordered)

        if batch_number + 1 < len(batch_starts):
            await asyncio.sleep(EMBED_INTER_BATCH_DELAY_SECONDS)

    return all_embeddings


async def embed_query(text: str) -> list[float]:
    embeddings = await embed_texts([text.strip()])
    return embeddings[0]
