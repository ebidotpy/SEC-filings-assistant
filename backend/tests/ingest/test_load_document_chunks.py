from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from ingest.chunking import ChunkRecord
from ingest.load_document_chunks import (
    chunk_rows,
    enrich_filing,
    ingest_filing,
    insert_document_chunks,
)


def test_enrich_filing_adds_fiscal_year():
    filing = {
        "ticker": "AAPL",
        "form": "10-K",
        "filing_date": "2025-10-31",
        "report_date": "2025-09-27",
        "accession_number": "0000320193-25-000079",
        "local_path": "2025/aapl.md",
    }
    enriched = enrich_filing(filing)
    assert enriched["fiscal_year"] == "2025"


def test_chunk_rows_aligns_records_and_embeddings():
    record = ChunkRecord(
        chunk_index=0,
        text="Sample text",
        embedding_text="Sample text",
        token_count=2,
        page=None,
        section="Item 1",
        chunk_metadata={"ticker": "TEST"},
    )
    rows = chunk_rows("doc-id", [record], [[0.1, 0.2]])
    assert len(rows) == 1
    assert rows[0]["document_id"] == "doc-id"
    assert rows[0]["chunk_index"] == 0
    assert rows[0]["embedding"] == [0.1, 0.2]


@pytest.mark.anyio
async def test_force_ingestion_preserves_existing_chunks_when_embeddings_fail(
    monkeypatch,
):
    document_id = uuid4()
    session = AsyncMock()
    session.add_all = MagicMock()
    monkeypatch.setattr(
        "ingest.load_document_chunks.chunk_records_for_filing",
        lambda *args, **kwargs: [_record(0)],
    )
    monkeypatch.setattr(
        "ingest.load_document_chunks.get_source_document_id",
        AsyncMock(return_value=document_id),
    )
    monkeypatch.setattr(
        "ingest.load_document_chunks.document_has_chunks", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "ingest.load_document_chunks.embed_texts",
        AsyncMock(side_effect=RuntimeError("provider unavailable")),
    )

    @asynccontextmanager
    async def sessions():
        yield session

    monkeypatch.setattr("ingest.load_document_chunks.get_db_session", sessions)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await ingest_filing(
            {"ticker": "TEST", "accession_number": "test"},
            dry_run=False,
            limit_chunks=None,
            skip_existing=True,
            force=True,
        )
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_failed_insert_batch_does_not_commit_partial_filing(monkeypatch):
    session = AsyncMock()
    session.add_all = MagicMock()
    session.flush.side_effect = [None, RuntimeError("database write failed")]

    @asynccontextmanager
    async def sessions():
        yield session

    records = [_record(i) for i in range(51)]
    monkeypatch.setattr("ingest.load_document_chunks.get_db_session", sessions)
    monkeypatch.setattr(
        "ingest.load_document_chunks.embed_texts",
        AsyncMock(return_value=[[0.1, 0.2]] * 51),
    )
    with pytest.raises(RuntimeError, match="database write failed"):
        await insert_document_chunks(uuid4(), records, replace_existing=True)
    assert session.flush.await_count == 2
    session.commit.assert_not_awaited()


def _record(index):
    return ChunkRecord(
        chunk_index=index,
        text="Sample text",
        embedding_text="Sample text",
        token_count=2,
        page=None,
        section="Item 1",
        chunk_metadata={},
    )
