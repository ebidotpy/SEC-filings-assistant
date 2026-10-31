"""LLM keyword extraction for Postgres full-text search."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings
from app.retrieval.types import SearchFilters

_INSTRUCTIONS_PATH = Path(__file__).resolve().parent / "keyword_instructions.md"


class SearchKeywords(BaseModel):
    terms: list[str] = Field(min_length=3, max_length=5)

    @field_validator("terms")
    @classmethod
    def non_empty_terms(cls, terms: list[str]) -> list[str]:
        cleaned = [term.strip() for term in terms if term.strip()]
        if len(cleaned) < 3 or len(cleaned) > 5:
            raise ValueError("terms must contain 3 to 5 non-empty strings")
        return cleaned


def load_keyword_instructions() -> str:
    return _INSTRUCTIONS_PATH.read_text(encoding="utf-8")


def _format_filter_context(filters: SearchFilters | None) -> str:
    if filters is None:
        return "None"

    parts: list[str] = []
    if filters.ticker is not None:
        parts.append(f"ticker={filters.ticker.upper()}")
    if filters.fiscal_year is not None:
        parts.append(f"fiscal_year={filters.fiscal_year}")
    if filters.form is not None:
        parts.append(f"form={filters.form.upper()}")

    return ", ".join(parts) if parts else "None"


def _build_prompt(query: str, filters: SearchFilters | None) -> str:
    return (
        f"Search query:\n{query}\n\nActive filters:\n{_format_filter_context(filters)}"
    )


def _build_keyword_agent() -> Agent[None, SearchKeywords]:
    model = OpenAIChatModel(
        settings.retrieval_keyword_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    )
    return Agent(
        model,
        name="keyword_extractor",
        output_type=SearchKeywords,
        instructions=load_keyword_instructions(),
    )


_keyword_agent = _build_keyword_agent()


async def extract_search_keywords(
    query: str,
    *,
    filters: SearchFilters | None = None,
) -> str:
    """Return 3–5 LLM-extracted terms joined for plainto_tsquery, or the raw query on failure."""
    query = query.strip()
    if not query:
        return query

    try:
        result = await _keyword_agent.run(
            _build_prompt(query, filters),
            model_settings={"temperature": settings.retrieval_keyword_temperature},
        )
        keywords = " ".join(result.output.terms)
        return keywords if keywords.strip() else query
    except Exception:  # noqa: BLE001
        return query
