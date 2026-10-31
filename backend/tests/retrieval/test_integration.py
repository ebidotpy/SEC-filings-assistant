from __future__ import annotations

import pytest
from app.database.documents import (
    close_db_engine,
    fulltext_search_chunk_ids,
    init_db_engine,
)
from app.retrieval.keywords import extract_search_keywords
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import SearchFilters


@pytest.mark.integration
@pytest.mark.anyio
async def test_apple_revenue_mix_query_returns_apple_chunks():
    await init_db_engine()
    try:
        retriever = DocumentRetriever()
        passages = await retriever.search(
            "Apple revenue mix iPhone Services Mac iPad Wearables 2021 2025",
            filters=SearchFilters(ticker="AAPL"),
            top_k=10,
        )
        assert passages
        assert all(passage.ticker == "AAPL" for passage in passages)
    finally:
        await close_db_engine()


@pytest.mark.integration
@pytest.mark.anyio
async def test_nvidia_data_center_query_returns_nvidia_chunks():
    await init_db_engine()
    try:
        retriever = DocumentRetriever()
        passages = await retriever.search(
            "NVIDIA Data Center demand drivers customer concentration supply constraints",
            filters=SearchFilters(ticker="NVDA"),
            top_k=10,
        )
        assert passages
        assert all(passage.ticker == "NVDA" for passage in passages)
    finally:
        await close_db_engine()


@pytest.mark.integration
@pytest.mark.anyio
async def test_keyword_extraction_improves_fulltext_hits():
    await init_db_engine()
    try:
        query = "Apple revenue mix iPhone Services Mac iPad Wearables 2021 2025"
        filters = SearchFilters(ticker="AAPL")

        raw_hits = await fulltext_search_chunk_ids(query, limit=20, filters=filters)
        keywords = await extract_search_keywords(query, filters=filters)
        extracted_hits = await fulltext_search_chunk_ids(
            keywords,
            limit=20,
            filters=filters,
        )

        assert len(extracted_hits) > len(raw_hits)
    finally:
        await close_db_engine()
