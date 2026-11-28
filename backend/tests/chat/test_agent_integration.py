from __future__ import annotations

import pytest
from openai import AsyncOpenAI, AuthenticationError
from sqlalchemy import text

from app.assistant.agent import document_agent, graph_config
from app.assistant.deps import DocumentAgentDeps, RetrievalRegistry
from app.config import settings
from app.database.session import close_db_engine, get_db_engine, init_db_engine
from app.grounding.validator import validate_grounded_answer
from app.retrieval.retriever import DocumentRetriever

pytestmark = [
    pytest.mark.integration,
    pytest.mark.anyio,
    pytest.mark.skipif(
        not settings.openai_api_key.strip()
        or settings.openai_api_key.startswith("mock-"),
        reason="Requires live OpenAI API key",
    ),
]


@pytest.fixture
async def agent_deps():
    await init_db_engine()
    try:
        async with AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.base_url,
            max_retries=0,
        ) as client:
            yield DocumentAgentDeps(
                retriever=DocumentRetriever(),
                registry=RetrievalRegistry(),
                client=client,
            )
    finally:
        await close_db_engine()


async def _has_filing_chunks(ticker: str) -> bool:
    try:
        async with get_db_engine().connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT 1
                    FROM document_chunks dc
                    JOIN source_documents sd ON sd.id = dc.document_id
                    WHERE sd.ticker = :ticker
                    LIMIT 1
                """),
                {"ticker": ticker},
            )
            return result.first() is not None
    except Exception:  # noqa: BLE001
        return False


async def _run_question(query: str, deps: DocumentAgentDeps):
    try:
        result = await document_agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]},
            context=deps,
            config=graph_config(),
        )
    except AuthenticationError as error:
        pytest.skip(f"OpenAI authentication failed: {error}")
    grounded = result["grounded_answer"]
    validate_grounded_answer(grounded, deps.registry)
    return grounded


async def test_agent_apple_revenue_mix_cites_filings_and_pages(agent_deps):
    if not await _has_filing_chunks("AAPL"):
        pytest.skip("Requires ingested AAPL filings in the database")
    grounded = await _run_question(
        "Across Apple's 2021-2025 10-Ks, how did the revenue mix between iPhone and Services change?",
        agent_deps,
    )

    assert grounded.insufficient_evidence is False
    assert grounded.citations
    cited_passages = [
        agent_deps.registry.passages[citation.chunk_id]
        for citation in grounded.citations
    ]
    assert all(passage.ticker == "AAPL" for passage in cited_passages)
    assert all(passage.form == "10-K" for passage in cited_passages)
    assert all(passage.page for passage in cited_passages)


async def test_agent_refuses_under_specified_question(agent_deps):
    grounded = await _run_question("Tell me about revenue.", agent_deps)

    assert grounded.insufficient_evidence is True
    assert not grounded.citations


async def test_agent_refuses_investment_advice_without_looping(agent_deps):
    grounded = await _run_question(
        "What is the best stock to buy right now?", agent_deps
    )

    assert grounded.insufficient_evidence is True
    assert not grounded.citations


async def test_agent_refuses_unanswerable_margin_inference(agent_deps):
    grounded = await _run_question(
        "Do the filings prove that generative AI improved margins for any of these companies?",
        agent_deps,
    )

    assert grounded.insufficient_evidence or not grounded.citations
