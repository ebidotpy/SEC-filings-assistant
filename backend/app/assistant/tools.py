from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic_ai import RunContext

from app.assistant.deps import DocumentAgentDeps
from app.retrieval.types import SearchFilters, SourcePassage

_TOOL_TEXT_LIMIT = 2000


def _passage_summary(passage: SourcePassage) -> dict[str, Any]:
    text = passage.text
    if len(text) > _TOOL_TEXT_LIMIT:
        text = text[: _TOOL_TEXT_LIMIT - 1].rstrip() + "…"

    return {
        "chunk_id": str(passage.chunk_id),
        "document_id": str(passage.document_id),
        "chunk_index": passage.chunk_index,
        "ticker": passage.ticker,
        "company_name": passage.company_name,
        "form": passage.form,
        "filing_date": passage.filing_date.isoformat(),
        "accession_number": passage.accession_number,
        "page": passage.page,
        "section": passage.section,
        "text": text,
    }


async def search_filings(
    ctx: RunContext[DocumentAgentDeps],
    query: str,
    ticker: str | None = None,
    fiscal_year: int | None = None,
    form: str | None = None,
) -> dict[str, Any]:
    """Hybrid-search SEC filing chunks. Returns result_count so a 0-result search is an explicit stop signal, not a bare empty list to keep retrying against."""
    filters = SearchFilters(ticker=ticker, fiscal_year=fiscal_year, form=form)
    passages = await ctx.deps.retriever.search(query, filters=filters)
    ctx.deps.registry.register_many(passages)
    return {
        "query": query,
        "result_count": len(passages),
        "results": [_passage_summary(passage) for passage in passages],
    }


async def read_chunk(
    ctx: RunContext[DocumentAgentDeps],
    chunk_id: UUID,
) -> dict[str, Any] | None:
    """Fetch one filing chunk by ID."""
    passage = await ctx.deps.retriever.get_chunk(chunk_id)
    if passage is None:
        return None
    ctx.deps.registry.register(passage)
    return _passage_summary(passage)


async def read_surrounding_chunks(
    ctx: RunContext[DocumentAgentDeps],
    chunk_id: UUID,
    radius: int = 1,
) -> list[dict[str, Any]]:
    """Fetch neighboring chunks around a filing chunk for additional context."""
    passages = await ctx.deps.retriever.get_surrounding_chunks(
        chunk_id,
        radius=radius,
    )
    ctx.deps.registry.register_many(passages)
    return [_passage_summary(passage) for passage in passages]
