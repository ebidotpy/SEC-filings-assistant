"""Hybrid retrieval: semantic + full-text search fused with RRF."""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.config import settings
from app.database import documents as document_db
from app.retrieval.embeddings import embed_query
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keywords import extract_search_keywords
from app.retrieval.queries import hybrid_search_chunk_ids
from app.retrieval.types import SearchFilters, SourcePassage


class DocumentRetriever:
    async def search(
        self,
        query: str,
        *,
        filters: SearchFilters | None = None,
        top_k: int | None = None,
        candidate_k: int | None = None,
    ) -> list[SourcePassage]:
        query = query.strip()
        if not query:
            return []

        candidate_k = candidate_k or settings.retrieval_candidate_k
        top_k = top_k or settings.retrieval_top_k

        embedding, fulltext_query = await asyncio.gather(
            embed_query(query),
            extract_search_keywords(query, filters=filters),
        )
        semantic_ids, fulltext_ids = await hybrid_search_chunk_ids(
            embedding,
            fulltext_query=fulltext_query,
            candidate_k=candidate_k,
            filters=filters,
            min_similarity=settings.retrieval_semantic_min_similarity,
        )
        fused = reciprocal_rank_fusion(
            [semantic_ids, fulltext_ids],
            k=settings.retrieval_rrf_k,
        )[:candidate_k]

        top_ids = [chunk_id for chunk_id, _ in fused[:top_k]]
        rrf_scores = {chunk_id: score for chunk_id, score in fused}
        return await document_db.fetch_passages_by_ids(top_ids, rrf_scores=rrf_scores)

    async def get_chunk(self, chunk_id: UUID) -> SourcePassage | None:
        return await document_db.fetch_passage_by_id(chunk_id)

    async def get_surrounding_chunks(
        self,
        chunk_id: UUID,
        *,
        radius: int | None = None,
    ) -> list[SourcePassage]:
        radius = radius if radius is not None else settings.retrieval_neighbor_radius
        passage = await document_db.fetch_passage_by_id(chunk_id)
        if passage is None:
            return []

        neighbor_ids = await document_db.fetch_neighbor_chunk_ids(
            passage.document_id,
            passage.chunk_index,
            radius=radius,
        )
        center = [passage]
        if not neighbor_ids:
            return center

        neighbors = await document_db.fetch_passages_by_ids(neighbor_ids)
        return sorted(
            center + neighbors,
            key=lambda item: (str(item.document_id), item.chunk_index),
        )
