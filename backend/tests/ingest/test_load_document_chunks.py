from __future__ import annotations

from ingest.chunking import ChunkRecord
from ingest.load_document_chunks import (
    chunk_rows,
    enrich_filing,
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
