from __future__ import annotations

from pathlib import Path

import pytest
from ingest.chunking import (
    build_chunker,
    chunk_document,
    chunk_document_hierarchical,
    extract_section,
    parse_markdown_to_docling,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
SAMPLE_FILING = FIXTURES_DIR / "sample_filing.md"

SAMPLE_FILING_META = {
    "ticker": "TEST",
    "form": "10-K",
    "accession_number": "0000000000-00-000001",
    "filing_date": "2025-01-01",
    "report_date": "2024-12-31",
    "fiscal_year": "2024",
}


@pytest.fixture(scope="module")
def sample_doc():
    return parse_markdown_to_docling(SAMPLE_FILING)


@pytest.fixture(scope="module")
def sample_records(sample_doc):
    chunker = build_chunker()
    return chunk_document(sample_doc, chunker, SAMPLE_FILING_META)


def test_extract_section_from_headings():
    assert extract_section("body", ["Part I", "Item 1. Business"]) == (
        "Part I > Item 1. Business"
    )


def test_extract_section_from_item_pattern():
    text = 'See Part II, Item 7, "Management\'s Discussion" for details.'
    assert extract_section(text, None) == "Part II, Item 7"


def test_chunk_document_returns_ordered_nonempty_records(sample_records):
    assert sample_records
    indices = [record.chunk_index for record in sample_records]
    assert indices == list(range(len(sample_records)))
    assert all(record.text.strip() for record in sample_records)
    assert all(record.token_count > 0 for record in sample_records)
    assert all(record.embedding_text for record in sample_records)


def test_chunk_metadata_includes_filing_fields(sample_records):
    metadata = sample_records[0].chunk_metadata
    assert metadata["ticker"] == "TEST"
    assert metadata["accession_number"] == "0000000000-00-000001"
    assert metadata["form"] == "10-K"


def test_contextualized_chunks_respect_token_limit(sample_records):
    from app.config import settings

    max_tokens = settings.openai_embedding_max_chunk_tokens
    for record in sample_records:
        assert record.token_count <= max_tokens + 1


def test_hierarchical_chunker_produces_structural_chunks(sample_doc):
    hierarchical = chunk_document_hierarchical(sample_doc)
    hybrid = chunk_document(sample_doc, build_chunker(), SAMPLE_FILING_META)
    assert hierarchical
    assert len(hybrid) <= len(hierarchical)
