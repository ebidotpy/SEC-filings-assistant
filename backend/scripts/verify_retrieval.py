"""Smoke-test hybrid retrieval against the ingested corpus."""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.database.documents import close_db_engine, init_db_engine
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import SearchFilters


async def run_query(
    query: str,
    *,
    ticker: str | None,
    top_k: int,
) -> None:
    await init_db_engine()
    try:
        retriever = DocumentRetriever()
        filters = SearchFilters(ticker=ticker) if ticker else None
        passages = await retriever.search(query, filters=filters, top_k=top_k)
        if not passages:
            print("No passages returned.")
            return

        print(f"Query: {query}\n")
        for index, passage in enumerate(passages, start=1):
            score = passage.rrf_score if passage.rrf_score is not None else 0.0
            print(
                f"{index}. [{score:.6f}] {passage.ticker} {passage.form} "
                f"({passage.filing_date}) p.{passage.page or '?'} "
                f"chunk={passage.chunk_index}"
            )
            excerpt = passage.text.replace("\n", " ")
            print(f"   {excerpt[:240]}{'...' if len(excerpt) > 240 else ''}\n")
    finally:
        await close_db_engine()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify hybrid retrieval against Supabase."
    )
    parser.add_argument("query", help="Natural-language search query")
    parser.add_argument("--ticker", help="Optional ticker filter (e.g. AAPL)")
    parser.add_argument(
        "--top-k", type=int, default=5, help="Number of passages to print"
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_query(args.query, ticker=args.ticker, top_k=args.top_k))
    except Exception as error:  # noqa: BLE001
        print(f"Retrieval failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
