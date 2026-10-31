from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from app.assistant.deps import DocumentAgentDeps, RetrievalRegistry
from app.assistant.tools import read_chunk, read_surrounding_chunks, search_filings
from app.retrieval.types import SearchFilters, SourcePassage
from pydantic_ai import RunContext

CHUNK_A = UUID("00000000-0000-0000-0000-000000000001")
CHUNK_B = UUID("00000000-0000-0000-0000-000000000002")


def _passage(chunk_id: UUID, chunk_index: int, text: str) -> SourcePassage:
    return SourcePassage(
        chunk_id=chunk_id,
        document_id=UUID("00000000-0000-0000-0000-000000000010"),
        chunk_index=chunk_index,
        text=text,
        ticker="NVDA",
        company_name="NVIDIA Corporation",
        form="10-K",
        filing_date=date(2025, 2, 26),
        accession_number="0001045810-25-000023",
        page="18",
        section="Business",
    )


def _ctx(
    retriever: AsyncMock, registry: RetrievalRegistry
) -> RunContext[DocumentAgentDeps]:
    deps = DocumentAgentDeps(retriever=retriever, registry=registry)
    return RunContext(
        deps=deps,
        model=MagicMock(),
        usage=MagicMock(),
        prompt="test",
        run_id="run-test",
    )


@pytest.mark.anyio
async def test_search_filings_registers_passages():
    passages = [_passage(CHUNK_A, 0, "Data Center demand increased.")]
    retriever = AsyncMock()
    retriever.search = AsyncMock(return_value=passages)
    registry = RetrievalRegistry()
    ctx = _ctx(retriever, registry)

    results = await search_filings(ctx, "Data Center demand", ticker="NVDA")

    retriever.search.assert_awaited_once_with(
        "Data Center demand",
        filters=SearchFilters(ticker="NVDA", fiscal_year=None, form=None),
    )
    assert results["result_count"] == 1
    assert len(results["results"]) == 1
    assert results["results"][0]["chunk_id"] == str(CHUNK_A)
    assert CHUNK_A in registry.passages


@pytest.mark.anyio
async def test_search_filings_reports_zero_result_count():
    retriever = AsyncMock()
    retriever.search = AsyncMock(return_value=[])
    registry = RetrievalRegistry()
    ctx = _ctx(retriever, registry)

    results = await search_filings(ctx, "best stock to buy")

    assert results["result_count"] == 0
    assert results["results"] == []
    assert results["query"] == "best stock to buy"


@pytest.mark.anyio
async def test_read_chunk_registers_single_passage():
    passage = _passage(CHUNK_B, 3, "Supply constraints eased.")
    retriever = AsyncMock()
    retriever.get_chunk = AsyncMock(return_value=passage)
    registry = RetrievalRegistry()
    ctx = _ctx(retriever, registry)

    result = await read_chunk(ctx, CHUNK_B)

    assert result is not None
    assert result["chunk_id"] == str(CHUNK_B)
    assert CHUNK_B in registry.passages


@pytest.mark.anyio
async def test_read_surrounding_chunks_registers_neighbors():
    center = _passage(CHUNK_B, 3, "Center chunk")
    neighbor = _passage(CHUNK_A, 2, "Neighbor chunk")
    retriever = AsyncMock()
    retriever.get_surrounding_chunks = AsyncMock(return_value=[neighbor, center])
    registry = RetrievalRegistry()
    ctx = _ctx(retriever, registry)

    results = await read_surrounding_chunks(ctx, CHUNK_B, radius=1)

    retriever.get_surrounding_chunks.assert_awaited_once_with(CHUNK_B, radius=1)
    assert len(results) == 2
    assert CHUNK_A in registry.passages
    assert CHUNK_B in registry.passages
