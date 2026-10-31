from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.retrieval.keywords import (
    SearchKeywords,
    _build_prompt,
    extract_search_keywords,
)
from app.retrieval.types import SearchFilters
from pydantic import ValidationError


def test_search_keywords_requires_three_to_five_non_empty_terms():
    assert SearchKeywords(terms=["iPhone", "Services", "revenue"]).terms == [
        "iPhone",
        "Services",
        "revenue",
    ]

    with pytest.raises(ValidationError):
        SearchKeywords(terms=["iPhone", "  ", "revenue"])

    with pytest.raises(ValidationError):
        SearchKeywords(terms=["one", "two"])


def test_build_prompt_includes_query_and_filters():
    prompt = _build_prompt(
        "What was Apple's iPhone revenue?",
        SearchFilters(ticker="AAPL", fiscal_year=2023, form="10-K"),
    )
    assert "What was Apple's iPhone revenue?" in prompt
    assert "ticker=AAPL" in prompt
    assert "fiscal_year=2023" in prompt
    assert "form=10-K" in prompt


@pytest.mark.anyio
async def test_extract_search_keywords_returns_joined_terms():
    mock_result = MagicMock()
    mock_result.output = SearchKeywords(terms=["iPhone", "Services", "revenue", "mix"])

    with patch(
        "app.retrieval.keywords._keyword_agent.run",
        new=AsyncMock(return_value=mock_result),
    ) as run:
        keywords = await extract_search_keywords(
            "Apple revenue mix iPhone Services Mac iPad Wearables 2021 2025",
            filters=SearchFilters(ticker="AAPL"),
        )

    assert keywords == "iPhone Services revenue mix"
    run.assert_awaited_once()
    prompt = run.await_args.args[0]
    assert "ticker=AAPL" in prompt


@pytest.mark.anyio
async def test_extract_search_keywords_falls_back_on_error():
    with patch(
        "app.retrieval.keywords._keyword_agent.run",
        new=AsyncMock(side_effect=RuntimeError("model unavailable")),
    ):
        query = "NVIDIA Data Center demand drivers"
        assert await extract_search_keywords(query) == query


@pytest.mark.anyio
async def test_extract_search_keywords_empty_query_short_circuits():
    with patch(
        "app.retrieval.keywords._keyword_agent.run",
        new=AsyncMock(),
    ) as run:
        assert await extract_search_keywords("   ") == ""
        run.assert_not_awaited()
