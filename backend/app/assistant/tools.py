from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from openai import pydantic_function_tool
from openai.types.chat import ChatCompletionFunctionToolParam
from pydantic import BaseModel, Field, ValidationError

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
    deps: DocumentAgentDeps,
    query: str,
    ticker: str | None = None,
    fiscal_year: int | None = None,
    form: str | None = None,
) -> dict[str, Any]:
    """Hybrid-search SEC filing chunks. Returns result_count so a 0-result search is an explicit stop signal, not a bare empty list to keep retrying against."""
    filters = SearchFilters(ticker=ticker, fiscal_year=fiscal_year, form=form)
    passages = await deps.retriever.search(query, filters=filters)
    deps.registry.register_many(passages)
    return {
        "query": query,
        "result_count": len(passages),
        "results": [_passage_summary(passage) for passage in passages],
    }


async def read_chunk(
    deps: DocumentAgentDeps,
    chunk_id: UUID,
) -> dict[str, Any] | None:
    """Fetch one filing chunk by ID."""
    passage = await deps.retriever.get_chunk(chunk_id)
    if passage is None:
        return None
    deps.registry.register(passage)
    return _passage_summary(passage)


async def read_surrounding_chunks(
    deps: DocumentAgentDeps,
    chunk_id: UUID,
    radius: int = 1,
) -> list[dict[str, Any]]:
    """Fetch neighboring chunks around a filing chunk for additional context."""
    passages = await deps.retriever.get_surrounding_chunks(
        chunk_id,
        radius=radius,
    )
    deps.registry.register_many(passages)
    return [_passage_summary(passage) for passage in passages]


class SearchFilingsArgs(BaseModel):
    query: str = Field(min_length=1)
    ticker: str | None = None
    fiscal_year: int | None = None
    form: str | None = None


class ReadChunkArgs(BaseModel):
    chunk_id: UUID


class ReadSurroundingChunksArgs(ReadChunkArgs):
    radius: int = Field(default=1, ge=0)


_TOOLS: dict[str, tuple[type[BaseModel], Callable[..., Awaitable[Any]]]] = {
    "search_filings": (SearchFilingsArgs, search_filings),
    "read_chunk": (ReadChunkArgs, read_chunk),
    "read_surrounding_chunks": (ReadSurroundingChunksArgs, read_surrounding_chunks),
}


def tool_definitions() -> list[ChatCompletionFunctionToolParam]:
    return [
        pydantic_function_tool(schema, name=name, description=tool.__doc__)
        for name, (schema, tool) in _TOOLS.items()
    ]


async def run_tool(
    name: str,
    arguments: str,
    deps: DocumentAgentDeps,
    *,
    status_writer: Callable[[str], None],
) -> str:
    if name not in _TOOLS:
        return json.dumps({"error": f"Unknown retrieval tool: {name}"})
    schema, tool = _TOOLS[name]
    try:
        args = schema.model_validate_json(arguments).model_dump()
    except ValidationError as error:
        return json.dumps({"error": str(error)})

    if name == "search_filings":
        ticker = args.get("ticker")
        status_writer(
            f"Searching filings for {ticker}…" if ticker else "Searching filings…"
        )
    else:
        status_writer("Reading filing passages…")
    result = await tool(deps, **args)
    return json.dumps(result, ensure_ascii=False)
