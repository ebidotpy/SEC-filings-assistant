"""Hybrid search query wrappers over document_chunks."""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.database import documents as document_db
from app.retrieval.types import SearchFilters


async def hybrid_search_chunk_ids(
    embedding: list[float],
    *,
    fulltext_query: str,
    candidate_k: int,
    filters: SearchFilters | None = None,
    min_similarity: float = 0.0,
) -> tuple[list[UUID], list[UUID]]:
    semantic_ids, fulltext_ids = await asyncio.gather(
        document_db.semantic_search_chunk_ids(
            embedding,
            limit=candidate_k,
            filters=filters,
            min_similarity=min_similarity,
        ),
        document_db.fulltext_search_chunk_ids(
            fulltext_query,
            limit=candidate_k,
            filters=filters,
        ),
    )
    return semantic_ids, fulltext_ids
