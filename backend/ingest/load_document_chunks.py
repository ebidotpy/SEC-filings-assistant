"""Chunk Markdown filings, embed passages, and write document_chunks to PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

from app.database.models.document_chunk import DocumentChunk
from app.database.models.source_document import SourceDocument
from app.database.session import get_db_session
from ingest.chunking import (
    ChunkRecord,
    build_chunker,
    chunk_document,
    parse_markdown_to_docling,
)
from ingest.embeddings import embed_texts
from sqlalchemy import delete, select

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MARKDOWN_DIR = REPO_ROOT / "data" / "Markdown"
MANIFEST_PATH = MARKDOWN_DIR / "manifest.json"
SKIP_EXISTING = True
INSERT_BATCH_SIZE = 50


def fiscal_year_from_filing(filing: dict[str, str]) -> int | None:
    report_date = filing.get("report_date")
    if report_date:
        return date.fromisoformat(report_date).year
    filing_date = filing.get("filing_date")
    return date.fromisoformat(filing_date).year if filing_date else None


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def enrich_filing(filing: dict[str, str]) -> dict[str, str]:
    enriched = dict(filing)
    fiscal_year = fiscal_year_from_filing(filing)
    if fiscal_year is not None:
        enriched["fiscal_year"] = str(fiscal_year)
    return enriched


def chunk_records_for_filing(
    filing: dict[str, str],
    *,
    limit_chunks: int | None = None,
) -> list[ChunkRecord]:
    markdown_path = MARKDOWN_DIR / filing["local_path"]
    if not markdown_path.is_file():
        raise FileNotFoundError(f"Missing Markdown file: {markdown_path}")

    doc = parse_markdown_to_docling(markdown_path)
    chunker = build_chunker()
    records = chunk_document(doc, chunker, enrich_filing(filing))
    if limit_chunks is not None:
        records = records[:limit_chunks]
    return records


def print_dry_run_stats(filing: dict[str, str], records: list[ChunkRecord]) -> None:
    token_counts = [r.token_count for r in records if r.token_count is not None]
    total_tokens = sum(token_counts)
    avg_tokens = (total_tokens / len(token_counts)) if token_counts else 0
    print(
        f"  [dry-run] {filing['ticker']} {filing['accession_number']}: "
        f"{len(records)} chunks, ~{total_tokens:,} tokens (avg {avg_tokens:.1f})"
    )
    if records:
        sample = records[min(15, len(records) - 1)]
        print(f"  sample section: {sample.section!r}")
        print(f"  sample text: {sample.text[:120]!r}...")


def chunk_rows(
    document_id: str | UUID,
    records: list[ChunkRecord],
    embeddings: list[list[float]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record, embedding in zip(records, embeddings, strict=True):
        rows.append(
            {
                "id": str(uuid4()),
                "document_id": str(document_id),
                "chunk_index": record.chunk_index,
                "page": record.page,
                "section": record.section,
                "text": record.text,
                "embedding": embedding,
                "token_count": record.token_count,
                "chunk_metadata": record.chunk_metadata,
            }
        )
    return rows


async def get_source_document_id(accession_number: str) -> UUID | None:
    async with get_db_session() as session:
        result = await session.execute(
            select(SourceDocument.id).where(
                SourceDocument.accession_number == accession_number
            )
        )
        return result.scalar_one_or_none()


async def document_has_chunks(document_id: UUID) -> bool:
    async with get_db_session() as session:
        result = await session.execute(
            select(DocumentChunk.id)
            .where(DocumentChunk.document_id == document_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None


async def delete_document_chunks(document_id: UUID) -> None:
    async with get_db_session() as session:
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await session.commit()


async def insert_document_chunks(
    document_id: UUID,
    records: list[ChunkRecord],
) -> int:
    embeddings = await embed_texts([record.embedding_text for record in records])

    chunks = [
        DocumentChunk(
            id=uuid4(),
            document_id=document_id,
            chunk_index=record.chunk_index,
            page=record.page,
            section=record.section,
            text=record.text,
            embedding=embedding,
            token_count=record.token_count,
            chunk_metadata=record.chunk_metadata or {},
        )
        for record, embedding in zip(records, embeddings, strict=True)
    ]

    async with get_db_session() as session:
        for start in range(0, len(chunks), INSERT_BATCH_SIZE):
            batch = chunks[start : start + INSERT_BATCH_SIZE]
            session.add_all(batch)
            await session.commit()

    return len(chunks)


async def ingest_filing(
    filing: dict[str, str],
    *,
    dry_run: bool,
    limit_chunks: int | None,
    skip_existing: bool,
    force: bool,
) -> str:
    accession_number = filing["accession_number"]
    records = chunk_records_for_filing(filing, limit_chunks=limit_chunks)

    if dry_run:
        print_dry_run_stats(filing, records)
        return "dry_run"

    document_id = await get_source_document_id(accession_number)
    if document_id is None:
        raise ValueError(
            f"No source_documents row for accession {accession_number}. "
            "Run ingest/load_source_documents.py first."
        )

    has_chunks = await document_has_chunks(document_id)
    if has_chunks and skip_existing and not force:
        return "skipped"

    if has_chunks and force:
        await delete_document_chunks(document_id)

    inserted = await insert_document_chunks(document_id, records)
    print(f"  {filing['ticker']} {accession_number}: inserted {inserted} chunk(s)")
    return "inserted"


async def load_document_chunks(
    *,
    accession_number: str | None,
    dry_run: bool,
    limit_chunks: int | None,
    skip_existing: bool,
    force: bool,
) -> dict[str, int]:
    manifest = load_manifest(MANIFEST_PATH)
    filings = manifest.get("filings", [])
    if not filings:
        raise ValueError(f"No filings listed in {MANIFEST_PATH}")

    if accession_number is not None:
        filings = [f for f in filings if f["accession_number"] == accession_number]
        if not filings:
            raise ValueError(
                f"Accession number not found in manifest: {accession_number}"
            )

    counts = {"inserted": 0, "skipped": 0, "dry_run": 0}

    for index, filing in enumerate(filings, start=1):
        print(
            f"[{index}/{len(filings)}] Processing {filing['ticker']} "
            f"{filing['accession_number']}..."
        )
        result = await ingest_filing(
            filing,
            dry_run=dry_run,
            limit_chunks=limit_chunks,
            skip_existing=skip_existing,
            force=force,
        )
        counts[result] += 1

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chunk Markdown filings, embed passages, and load document_chunks."
    )
    parser.add_argument(
        "--accession-number",
        help="Process a single filing by accession number.",
    )
    parser.add_argument(
        "--limit-chunks",
        type=int,
        help="Stop after N chunks per document (for smoke tests).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk filings without writing to database.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing chunks and reload.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all filings without skipping.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = asyncio.run(
        load_document_chunks(
            accession_number=args.accession_number,
            dry_run=args.dry_run,
            limit_chunks=args.limit_chunks,
            skip_existing=not args.all,
            force=args.force,
        )
    )
    print(
        f"Completed: {results.get('inserted', 0)} inserted, "
        f"{results.get('skipped', 0)} skipped, "
        f"{results.get('dry_run', 0)} dry-run"
    )


if __name__ == "__main__":
    main()
