"""Load Markdown filings from data/Markdown into source_documents."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from app.database.models.source_document import SourceDocument
from app.database.session import get_db_session
from sqlalchemy import select

# Params: edit these, then run from backend/:
#   uv run python ingest/load_source_documents.py
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MARKDOWN_DIR = REPO_ROOT / "data" / "Markdown"
MANIFEST_PATH = MARKDOWN_DIR / "manifest.json"
SKIP_EXISTING = True

COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


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


async def upsert_source_document(
    filing: dict[str, str],
    markdown_path: Path,
) -> str:
    accession_number = filing["accession_number"]
    async with get_db_session() as session:
        result = await session.execute(
            select(SourceDocument).where(
                SourceDocument.accession_number == accession_number
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None and SKIP_EXISTING:
            return "skipped"

        markdown_content = markdown_path.read_text(encoding="utf-8")
        ticker = filing["ticker"]

        if existing is not None:
            existing.ticker = ticker
            existing.cik = filing["cik"]
            existing.company_name = COMPANY_NAMES.get(ticker)
            existing.form = filing["form"]
            existing.filing_date = parse_date(filing.get("filing_date")) or date.today()
            existing.report_date = parse_date(filing.get("report_date"))
            existing.fiscal_year = fiscal_year_from_filing(filing)
            existing.primary_document = filing["primary_document"]
            existing.source_url = filing["source_url"]
            existing.markdown_content = markdown_content
            existing.ingested_at = datetime.now(UTC)
            await session.commit()
            return "updated"

        doc = SourceDocument(
            id=uuid4(),
            ticker=ticker,
            cik=filing["cik"],
            company_name=COMPANY_NAMES.get(ticker),
            form=filing["form"],
            filing_date=parse_date(filing.get("filing_date")) or date.today(),
            report_date=parse_date(filing.get("report_date")),
            fiscal_year=fiscal_year_from_filing(filing),
            accession_number=accession_number,
            primary_document=filing["primary_document"],
            source_url=filing["source_url"],
            markdown_content=markdown_content,
            ingested_at=datetime.now(UTC),
        )
        session.add(doc)
        await session.commit()
        return "inserted"


async def load_source_documents() -> dict[str, int]:
    manifest = load_manifest(MANIFEST_PATH)
    filings = manifest.get("filings", [])
    if not filings:
        raise ValueError(f"No filings listed in {MANIFEST_PATH}")

    counts = {"inserted": 0, "updated": 0, "skipped": 0}

    for index, filing in enumerate(filings, start=1):
        markdown_path = MARKDOWN_DIR / filing["local_path"]
        if not markdown_path.is_file():
            raise FileNotFoundError(f"Missing Markdown file: {markdown_path}")

        print(
            f"[{index}/{len(filings)}] Loading {filing['ticker']} "
            f"{filing['accession_number']}..."
        )
        result = await upsert_source_document(filing, markdown_path)
        counts[result] += 1

    return counts


def main() -> None:
    result = asyncio.run(load_source_documents())
    print(
        "Loaded source documents: "
        f"{result['inserted']} inserted, "
        f"{result['updated']} updated, "
        f"{result['skipped']} skipped"
    )


if __name__ == "__main__":
    main()
