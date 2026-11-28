from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from app.retrieval.keywords import (
    SearchKeywords,
    _build_prompt,
    extract_search_keywords,
)
from app.retrieval.types import SearchFilters


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
async def test_extract_search_keywords_returns_joined_terms(
    mock_openai, model_completion
):
    mock_openai.responses.append(
        model_completion(
            content=json.dumps({"terms": ["iPhone", "Services", "revenue", "mix"]})
        )
    )

    with patch("app.retrieval.keywords.AsyncOpenAI", return_value=mock_openai.client):
        keywords = await extract_search_keywords(
            "Apple revenue mix iPhone Services Mac iPad Wearables 2021 2025",
            filters=SearchFilters(ticker="AAPL"),
        )

    assert keywords == "iPhone Services revenue mix"
    assert len(mock_openai.requests) == 1
    prompt = mock_openai.requests[0]["messages"][-1]["content"]
    assert "ticker=AAPL" in prompt
    assert mock_openai.requests[0]["response_format"]["json_schema"]["strict"] is True
    assert "temperature" not in mock_openai.requests[0]


@pytest.mark.anyio
async def test_extract_search_keywords_falls_back_on_api_error(mock_openai):
    mock_openai.responses.append(
        httpx.Response(503, json={"error": {"message": "model unavailable"}})
    )
    with patch("app.retrieval.keywords.AsyncOpenAI", return_value=mock_openai.client):
        query = "NVIDIA Data Center demand drivers"
        assert await extract_search_keywords(query) == query


@pytest.mark.anyio
@pytest.mark.parametrize("content", ["not JSON", '{"terms": ["one", "two"]}', None])
async def test_extract_search_keywords_falls_back_on_invalid_output(
    mock_openai, model_completion, content
):
    mock_openai.responses.append(model_completion(content=content))
    with patch("app.retrieval.keywords.AsyncOpenAI", return_value=mock_openai.client):
        query = "NVIDIA Data Center demand drivers"
        assert await extract_search_keywords(query) == query


@pytest.mark.anyio
async def test_extract_search_keywords_empty_query_short_circuits():
    with patch(
        "app.retrieval.keywords.AsyncOpenAI",
    ) as client:
        assert await extract_search_keywords("   ") == ""
        client.assert_not_called()
