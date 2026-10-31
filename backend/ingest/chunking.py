"""Docling-based document chunking for SEC filing ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tiktoken
from app.config import settings
from docling.chunking import HierarchicalChunker, HybridChunker
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.types.doc.document import DoclingDocument

_ITEM_SECTION_RE = re.compile(
    r"(?:Part\s+[IVXLC]+,\s*)?Item\s+\d+[A-Z]?\.?(?:\s*[\"'][^\"']+[\"'])?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChunkRecord:
    chunk_index: int
    text: str
    embedding_text: str
    token_count: int
    page: str | None
    section: str | None
    chunk_metadata: dict[str, Any]


def build_tokenizer() -> OpenAITokenizer:
    encoding = tiktoken.encoding_for_model(settings.openai_embedding_model)
    return OpenAITokenizer(
        tokenizer=encoding,
        max_tokens=settings.openai_embedding_max_chunk_tokens,
    )


def build_chunker(tokenizer: OpenAITokenizer | None = None) -> HybridChunker:
    tokenizer = tokenizer or build_tokenizer()
    return HybridChunker(
        tokenizer=tokenizer,
        merge_peers=True,
        repeat_table_header=True,
    )


def parse_markdown_to_docling(path: Path) -> DoclingDocument:
    result = DocumentConverter().convert(str(path))
    return result.document


def extract_page(meta: Any) -> str | None:
    for item in meta.doc_items or []:
        for prov in getattr(item, "prov", None) or []:
            page_no = getattr(prov, "page_no", None)
            if page_no is not None:
                return str(page_no)
    return None


def extract_section(text: str, headings: list[str] | None) -> str | None:
    if headings:
        return " > ".join(headings)
    match = _ITEM_SECTION_RE.search(text)
    return match.group(0) if match else None


def build_chunk_metadata(
    chunk: Any,
    filing: dict[str, str],
    *,
    headings: list[str] | None,
    captions: list[str] | None,
) -> dict[str, Any]:
    return {
        "ticker": filing["ticker"],
        "form": filing["form"],
        "fiscal_year": filing.get("fiscal_year"),
        "accession_number": filing["accession_number"],
        "filing_date": filing.get("filing_date"),
        "headings": headings or [],
        "captions": captions or [],
    }


def chunk_document(
    doc: DoclingDocument,
    chunker: HybridChunker,
    filing: dict[str, str],
) -> list[ChunkRecord]:
    tokenizer = chunker.tokenizer
    records: list[ChunkRecord] = []

    for chunk_index, chunk in enumerate(chunker.chunk(dl_doc=doc)):
        embedding_text = chunker.contextualize(chunk=chunk)
        headings = chunk.meta.headings
        records.append(
            ChunkRecord(
                chunk_index=chunk_index,
                text=chunk.text,
                embedding_text=embedding_text,
                token_count=tokenizer.count_tokens(text=embedding_text),
                page=extract_page(chunk.meta),
                section=extract_section(chunk.text, headings),
                chunk_metadata=build_chunk_metadata(
                    chunk,
                    filing,
                    headings=headings,
                    captions=None,
                ),
            )
        )

    return records


def chunk_document_hierarchical(doc: DoclingDocument) -> list[str]:
    """Return raw text chunks from HierarchicalChunker (debug / tests)."""
    return [chunk.text for chunk in HierarchicalChunker().chunk(dl_doc=doc)]
