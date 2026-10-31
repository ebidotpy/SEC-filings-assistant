from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import SearchFilters, SourcePassage

A = UUID("00000000-0000-0000-0000-000000000001")
B = UUID("00000000-0000-0000-0000-000000000002")
C = UUID("00000000-0000-0000-0000-000000000003")


def _passage(chunk_id: UUID, *, chunk_index: int = 0) -> SourcePassage:
    return SourcePassage(
        chunk_id=chunk_id,
        document_id=UUID("10000000-0000-0000-0000-000000000001"),
        chunk_index=chunk_index,
        text=f"text for {chunk_id}",
        ticker="AAPL",
        company_name="Apple Inc.",
        form="10-K",
        filing_date=date(2024, 10, 31),
        accession_number="0000320193-24-000123",
    )


@pytest.mark.anyio
async def test_search_fuses_and_hydrates_passages():
    retriever = DocumentRetriever()

    with (
        patch(
            "app.retrieval.retriever.embed_query",
            new=AsyncMock(return_value=[0.1, 0.2]),
        ),
        patch(
            "app.retrieval.retriever.extract_search_keywords",
            new=AsyncMock(return_value="revenue mix iPhone"),
        ),
        patch(
            "app.retrieval.retriever.hybrid_search_chunk_ids",
            new=AsyncMock(return_value=([A, B], [B, C])),
        ),
        patch(
            "app.retrieval.retriever.document_db.fetch_passages_by_ids",
            new=AsyncMock(
                side_effect=lambda ids, rrf_scores=None: [
                    _passage(chunk_id, chunk_index=index).model_copy(
                        update={
                            "rrf_score": rrf_scores.get(chunk_id)
                            if rrf_scores
                            else None
                        }
                    )
                    for index, chunk_id in enumerate(ids)
                ]
            ),
        ) as fetch,
    ):
        results = await retriever.search("Apple revenue mix", top_k=2)

    assert [passage.chunk_id for passage in results] == [B, A]
    assert results[0].rrf_score is not None
    assert results[0].rrf_score > results[1].rrf_score
    fetch.assert_awaited_once()
    assert (
        fetch.await_args.kwargs["rrf_scores"][B]
        > fetch.await_args.kwargs["rrf_scores"][A]
    )


@pytest.mark.anyio
async def test_search_empty_query_returns_no_results():
    retriever = DocumentRetriever()
    assert await retriever.search("   ") == []


@pytest.mark.anyio
async def test_get_surrounding_chunks_includes_center_and_neighbors():
    retriever = DocumentRetriever()
    center = _passage(A, chunk_index=5)
    left = _passage(B, chunk_index=4)
    right = _passage(C, chunk_index=6)

    with (
        patch(
            "app.retrieval.retriever.document_db.fetch_passage_by_id",
            new=AsyncMock(return_value=center),
        ),
        patch(
            "app.retrieval.retriever.document_db.fetch_neighbor_chunk_ids",
            new=AsyncMock(return_value=[B, C]),
        ),
        patch(
            "app.retrieval.retriever.document_db.fetch_passages_by_ids",
            new=AsyncMock(return_value=[left, right]),
        ),
    ):
        results = await retriever.get_surrounding_chunks(A, radius=1)

    assert [passage.chunk_id for passage in results] == [B, A, C]


@pytest.mark.anyio
async def test_search_passes_filters():
    retriever = DocumentRetriever()
    filters = SearchFilters(ticker="AAPL", fiscal_year=2024)

    with (
        patch("app.retrieval.retriever.embed_query", new=AsyncMock(return_value=[0.1])),
        patch(
            "app.retrieval.retriever.extract_search_keywords",
            new=AsyncMock(return_value="revenue"),
        ),
        patch(
            "app.retrieval.retriever.hybrid_search_chunk_ids",
            new=AsyncMock(return_value=([A], [])),
        ) as hybrid,
        patch(
            "app.retrieval.retriever.document_db.fetch_passages_by_ids",
            new=AsyncMock(return_value=[_passage(A)]),
        ),
    ):
        await retriever.search("revenue", filters=filters)

    assert hybrid.await_args.kwargs["fulltext_query"] == "revenue"
    assert hybrid.await_args.kwargs["filters"] == filters
