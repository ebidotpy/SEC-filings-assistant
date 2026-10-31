"""Smoke-test grounded agent answers against the ingested corpus."""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.observability import configure_logfire
from pydantic_ai.exceptions import UnexpectedModelBehavior

configure_logfire()

from app.assistant.agent import document_agent, usage_limits
from app.assistant.deps import DocumentAgentDeps, RetrievalRegistry
from app.config import settings
from app.database.documents import close_db_engine, init_db_engine
from app.grounding.validator import GroundingError, validate_grounded_answer
from app.retrieval.retriever import DocumentRetriever


async def run_question(query: str) -> int:
    await init_db_engine()
    try:
        registry = RetrievalRegistry()
        deps = DocumentAgentDeps(
            retriever=DocumentRetriever(),
            registry=registry,
        )
        result = await document_agent.run(
            query,
            deps=deps,
            usage_limits=usage_limits(),
            model_settings={"temperature": settings.agent_temperature},
        )
        grounded = result.output
        validate_grounded_answer(grounded, registry)

        print(f"Question: {query}\n")
        print(grounded.answer)
        print()
        if grounded.insufficient_evidence:
            print("Evidence status: insufficient")
            return 0

        print(f"Citations: {len(grounded.citations)}")
        for citation in grounded.citations:
            passage = registry.passages[citation.chunk_id]
            print(
                f"  [{citation.citation_index}] {passage.ticker} {passage.form} "
                f"({passage.filing_date}) p.{passage.page or '?'}"
            )
            print(f"      {citation.excerpt[:200]}")
        return 0
    except (GroundingError, UnexpectedModelBehavior) as error:
        print(f"Grounding validation failed: {error}", file=sys.stderr)
        return 1
    finally:
        await close_db_engine()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify grounded agent answers against Supabase corpus.",
    )
    parser.add_argument("query", help="Analyst question to ask the agent")
    args = parser.parse_args()

    try:
        return asyncio.run(run_question(args.query))
    except Exception as error:  # noqa: BLE001
        print(f"Agent run failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
