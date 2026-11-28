"""Smoke-test grounded agent answers against the ingested corpus."""

from __future__ import annotations

import argparse
import asyncio
import sys

from openai import AsyncOpenAI

from app.assistant.agent import AgentLimitError, document_agent, graph_config
from app.assistant.deps import DocumentAgentDeps, RetrievalRegistry
from app.config import settings
from app.database.session import close_db_engine, init_db_engine
from app.grounding.validator import GroundingError, validate_grounded_answer
from app.observability import configure_logfire
from app.retrieval.retriever import DocumentRetriever


async def run_question(query: str) -> int:
    await init_db_engine()
    try:
        registry = RetrievalRegistry()
        async with AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.base_url,
            max_retries=0,
        ) as client:
            deps = DocumentAgentDeps(
                retriever=DocumentRetriever(), registry=registry, client=client
            )
            result = await document_agent.ainvoke(
                {"messages": [{"role": "user", "content": query}]},
                context=deps,
                config=graph_config(),
            )
        grounded = result["grounded_answer"]
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
    except (GroundingError, AgentLimitError) as error:
        print(f"Agent validation or usage limit failed: {error}", file=sys.stderr)
        return 1
    finally:
        await close_db_engine()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify grounded agent answers against the ingested corpus.",
    )
    parser.add_argument("query", help="Analyst question to ask the agent")
    args = parser.parse_args()
    configure_logfire()

    try:
        return asyncio.run(run_question(args.query))
    except Exception as error:  # noqa: BLE001
        print(f"Agent run failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
