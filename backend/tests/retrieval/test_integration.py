from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.database.documents import fulltext_search_chunk_ids
from app.database.session import close_db_engine, get_db_engine, init_db_engine
from app.retrieval.keywords import extract_search_keywords
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import SearchFilters


def _is_live_openai_configured() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and not key.startswith("mock-"))


requires_live_openai = pytest.mark.skipif(
    not _is_live_openai_configured(),
    reason="Requires live OpenAI API key",
)


async def _has_filing_chunks(ticker: str) -> bool:
    try:
        sql = """
            SELECT 1
            FROM document_chunks dc
            JOIN source_documents sd ON sd.id = dc.document_id
            WHERE sd.ticker = :ticker
            LIMIT 1
        """
        async with get_db_engine().connect() as conn:
            result = await conn.execute(text(sql), {"ticker": ticker})
            return result.first() is not None
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.integration
@requires_live_openai
@pytest.mark.anyio
async def test_apple_revenue_mix_query_returns_apple_chunks():
    await init_db_engine()
    try:
        if not await _has_filing_chunks("AAPL"):
            pytest.skip("Requires ingested AAPL filings in the database")
        retriever = DocumentRetriever()
        try:
            passages = await retriever.search(
                "Apple revenue mix iPhone Services Mac iPad Wearables 2021 2025",
                filters=SearchFilters(ticker="AAPL"),
                top_k=10,
            )
        except Exception as e:
            if "AuthenticationError" in type(e).__name__:
                pytest.skip(f"OpenAI authentication failed: {e}")
            raise
        assert passages
        assert all(passage.ticker == "AAPL" for passage in passages)
    finally:
        await close_db_engine()


@pytest.mark.integration
@requires_live_openai
@pytest.mark.anyio
async def test_nvidia_data_center_query_returns_nvidia_chunks():
    await init_db_engine()
    try:
        if not await _has_filing_chunks("NVDA"):
            pytest.skip("Requires ingested NVDA filings in the database")
        retriever = DocumentRetriever()
        try:
            passages = await retriever.search(
                "NVIDIA Data Center demand drivers customer concentration supply constraints",
                filters=SearchFilters(ticker="NVDA"),
                top_k=10,
            )
        except Exception as e:
            if "AuthenticationError" in type(e).__name__:
                pytest.skip(f"OpenAI authentication failed: {e}")
            raise
        assert passages
        assert all(passage.ticker == "NVDA" for passage in passages)
    finally:
        await close_db_engine()


@pytest.mark.integration
@requires_live_openai
@pytest.mark.anyio
async def test_keyword_extraction_improves_fulltext_hits():
    await init_db_engine()
    try:
        if not await _has_filing_chunks("AAPL"):
            pytest.skip("Requires ingested AAPL filings in the database")
        query = "Apple revenue mix iPhone Services Mac iPad Wearables 2021 2025"
        filters = SearchFilters(ticker="AAPL")

        raw_hits = await fulltext_search_chunk_ids(query, limit=20, filters=filters)
        try:
            keywords = await extract_search_keywords(query, filters=filters)
        except Exception as e:
            if "AuthenticationError" in type(e).__name__:
                pytest.skip(f"OpenAI authentication failed: {e}")
            raise
        extracted_hits = await fulltext_search_chunk_ids(
            keywords,
            limit=20,
            filters=filters,
        )

        assert len(extracted_hits) > len(raw_hits)
    finally:
        await close_db_engine()
