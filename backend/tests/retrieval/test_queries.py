from __future__ import annotations

from app.database.documents import build_filter_clause, vector_literal
from app.retrieval.types import SearchFilters


def test_vector_literal_formats_pgvector_input():
    assert vector_literal([0.1, 0.2, 0.3]) == "[0.1,0.2,0.3]"


def test_build_filter_clause_empty_when_no_filters():
    sql, params = build_filter_clause(None)
    assert sql == ""
    assert params == {}


def test_build_filter_clause_includes_ticker_and_year():
    sql, params = build_filter_clause(
        SearchFilters(ticker="aapl", fiscal_year=2024, form="10-k")
    )
    assert "sd.ticker = :ticker" in sql
    assert "sd.fiscal_year = :fiscal_year" in sql
    assert "sd.form = :form" in sql
    assert params == {"ticker": "AAPL", "fiscal_year": 2024, "form": "10-K"}


def test_build_filter_clause_partial_filters():
    sql, params = build_filter_clause(SearchFilters(ticker="nvda"))
    assert sql == " AND sd.ticker = :ticker"
    assert params == {"ticker": "NVDA"}
