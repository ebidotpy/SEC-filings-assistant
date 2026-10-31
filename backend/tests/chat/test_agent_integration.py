from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from app.assistant.agent import document_agent, usage_limits
from app.assistant.deps import DocumentAgentDeps, RetrievalRegistry
from app.config import settings
from app.database.documents import close_db_engine, init_db_engine
from app.grounding.validator import validate_grounded_answer
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import SourcePassage
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

_CHUNK_ID = UUID("00000000-0000-0000-0000-000000000abc")


def _passage(text: str) -> SourcePassage:
    return SourcePassage(
        chunk_id=_CHUNK_ID,
        document_id=UUID("00000000-0000-0000-0000-000000000010"),
        chunk_index=0,
        text=text,
        ticker="AAPL",
        company_name="Apple Inc.",
        form="10-K",
        filing_date=date(2023, 11, 3),
        accession_number="0000320193-23-000106",
        page="21",
        section="Item 7",
    )


@pytest.mark.anyio
async def test_agent_retries_then_succeeds_on_ungrounded_citation():
    passage = _passage(
        "iPhone net sales decreased 2% or $4.9 billion during 2023 compared to 2022."
    )
    registry = RetrievalRegistry()
    registry.register(passage)
    deps = DocumentAgentDeps(retriever=DocumentRetriever(), registry=registry)

    calls = {"count": 0}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["count"] += 1
        if calls["count"] == 1:
            args = {
                "answer": "iPhone net sales fell. [1]",
                "citations": [
                    {
                        "citation_index": 1,
                        "chunk_id": str(_CHUNK_ID),
                        "excerpt": "iPhone revenue soared to record highs.",
                    }
                ],
                "insufficient_evidence": False,
            }
        else:
            args = {
                "answer": "iPhone net sales fell. [1]",
                "citations": [
                    {
                        "citation_index": 1,
                        "chunk_id": str(_CHUNK_ID),
                        "excerpt": (
                            "iPhone net sales decreased 2% or $4.9 billion during "
                            "2023 compared to 2022."
                        ),
                    }
                ],
                "insufficient_evidence": False,
            }
        return ModelResponse(parts=[ToolCallPart("final_result", args)])

    with document_agent.override(model=FunctionModel(respond)):
        result = await document_agent.run(
            "What did Apple's 10-K say about iPhone revenue in fiscal 2023?",
            deps=deps,
        )

    assert calls["count"] == 2
    grounded = result.output
    validate_grounded_answer(grounded, registry)
    assert grounded.citations[0].chunk_id == _CHUNK_ID


@pytest.mark.integration
@pytest.mark.anyio
async def test_agent_apple_revenue_mix_cites_filings_and_pages():
    await init_db_engine()
    try:
        registry = RetrievalRegistry()
        deps = DocumentAgentDeps(retriever=DocumentRetriever(), registry=registry)
        result = await document_agent.run(
            "Across Apple's 2021-2025 10-Ks, how did the revenue mix between iPhone and Services change?",
            deps=deps,
            usage_limits=usage_limits(),
            model_settings={"temperature": settings.agent_temperature},
        )
        grounded = result.output
        validate_grounded_answer(grounded, registry)
        assert grounded.insufficient_evidence is False
        assert grounded.citations

        cited_passages = [
            registry.passages[citation.chunk_id] for citation in grounded.citations
        ]
        assert all(passage.ticker == "AAPL" for passage in cited_passages)
        assert all(passage.form == "10-K" for passage in cited_passages)
        assert all(passage.page for passage in cited_passages)
    finally:
        await close_db_engine()


@pytest.mark.integration
@pytest.mark.anyio
async def test_agent_refuses_under_specified_question():
    await init_db_engine()
    try:
        registry = RetrievalRegistry()
        deps = DocumentAgentDeps(retriever=DocumentRetriever(), registry=registry)
        result = await document_agent.run(
            "Tell me about revenue.",
            deps=deps,
            usage_limits=usage_limits(),
            model_settings={"temperature": settings.agent_temperature},
        )
        grounded = result.output
        validate_grounded_answer(grounded, registry)
        assert grounded.insufficient_evidence is True
        assert not grounded.citations
    finally:
        await close_db_engine()


@pytest.mark.integration
@pytest.mark.anyio
async def test_agent_refuses_investment_advice_without_looping():
    await init_db_engine()
    try:
        registry = RetrievalRegistry()
        deps = DocumentAgentDeps(retriever=DocumentRetriever(), registry=registry)
        result = await document_agent.run(
            "What is the best stock to buy right now?",
            deps=deps,
            usage_limits=usage_limits(),
            model_settings={"temperature": settings.agent_temperature},
        )
        grounded = result.output
        validate_grounded_answer(grounded, registry)
        assert grounded.insufficient_evidence is True
        assert not grounded.citations
    finally:
        await close_db_engine()


@pytest.mark.integration
@pytest.mark.anyio
async def test_agent_refuses_unanswerable_margin_inference():
    await init_db_engine()
    try:
        registry = RetrievalRegistry()
        deps = DocumentAgentDeps(retriever=DocumentRetriever(), registry=registry)
        result = await document_agent.run(
            "Do the filings prove that generative AI improved margins for any of these companies?",
            deps=deps,
            usage_limits=usage_limits(),
            model_settings={"temperature": settings.agent_temperature},
        )
        grounded = result.output
        validate_grounded_answer(grounded, registry)
        assert grounded.insufficient_evidence or not grounded.citations
    finally:
        await close_db_engine()
