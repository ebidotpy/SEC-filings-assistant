"""OpenAI embedding generation for ingestion."""

from __future__ import annotations

from app.embeddings import (
    EMBED_BATCH_SIZE,
    EMBED_INTER_BATCH_DELAY_SECONDS,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES,
    OPENAI_EMBEDDING_MAX_INPUT_TOKENS,
    RETRYABLE_ERRORS,
    count_tokens,
    create_embeddings_with_retry,
    embed_texts,
    openai_client,
    validate_texts,
)

__all__ = [
    "EMBED_BATCH_SIZE",
    "EMBED_INTER_BATCH_DELAY_SECONDS",
    "INITIAL_BACKOFF_SECONDS",
    "MAX_BACKOFF_SECONDS",
    "MAX_RETRIES",
    "OPENAI_EMBEDDING_MAX_INPUT_TOKENS",
    "RETRYABLE_ERRORS",
    "count_tokens",
    "create_embeddings_with_retry",
    "embed_texts",
    "openai_client",
    "validate_texts",
]

# Backward-compatible aliases for existing tests.
_create_embeddings_with_retry = create_embeddings_with_retry
