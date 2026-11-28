from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.assistant.agent import AgentLimitError, document_agent, graph_config
from app.assistant.deps import DocumentAgentDeps, RetrievalRegistry
from app.config import settings
from app.grounding.validator import GroundingError, validate_grounded_answer
from app.retrieval.types import SearchFilters, SourcePassage

CHUNK_ID = UUID("00000000-0000-0000-0000-000000000001")


def _passage() -> SourcePassage:
    return SourcePassage(
        chunk_id=CHUNK_ID,
        document_id=UUID("00000000-0000-0000-0000-000000000010"),
        chunk_index=0,
        text="Services revenue increased over the period.",
        ticker="AAPL",
        company_name="Apple Inc.",
        form="10-K",
        filing_date=date(2024, 10, 31),
        accession_number="0000320193-24-000123",
        page="21",
    )


def _answer(*, excerpt: str | None = None) -> dict:
    return {
        "answer": "Services revenue increased over the period. [1]",
        "citations": [
            {
                "citation_index": 1,
                "chunk_id": str(CHUNK_ID),
                "excerpt": excerpt or _passage().text,
            }
        ],
        "insufficient_evidence": False,
    }


def _insufficient() -> dict:
    return {
        "answer": "The corpus does not contain enough evidence.",
        "citations": [],
        "insufficient_evidence": True,
    }


def _deps(client, *, retrieved: bool = False) -> DocumentAgentDeps:
    registry = RetrievalRegistry()
    if retrieved:
        registry.register(_passage())
    return DocumentAgentDeps(client=client, registry=registry, retriever=AsyncMock())


@pytest.mark.anyio
async def test_graph_searches_then_returns_a_validated_answer(
    mock_openai, model_completion, model_tool_call
):
    deps = _deps(mock_openai.client)
    deps.retriever.search.return_value = [_passage()]
    mock_openai.responses.extend(
        [
            model_completion(
                tool_calls=[
                    model_tool_call(
                        "search_filings",
                        {
                            "query": "Services revenue",
                            "ticker": "AAPL",
                            "fiscal_year": 2024,
                        },
                    )
                ]
            ),
            model_completion(tool_calls=[model_tool_call("submit_answer", _answer())]),
        ]
    )
    history = [
        {"role": "user", "content": "What does Apple report?"},
        {"role": "assistant", "content": "We were discussing Services."},
        {"role": "user", "content": "How did its revenue change?"},
    ]

    result = await document_agent.ainvoke(
        {"messages": history}, context=deps, config=graph_config()
    )

    grounded = result["grounded_answer"]
    validate_grounded_answer(grounded, deps.registry)
    assert grounded.citations[0].chunk_id == CHUNK_ID
    deps.retriever.search.assert_awaited_once_with(
        "Services revenue",
        filters=SearchFilters(ticker="AAPL", fiscal_year=2024),
    )
    assert mock_openai.requests[0]["messages"][1:] == history
    tool_reply = mock_openai.requests[1]["messages"][-1]
    assert tool_reply["role"] == "tool"
    assert '"result_count": 1' in tool_reply["content"]
    schemas = {
        tool["function"]["name"]: tool["function"]
        for tool in mock_openai.requests[0]["tools"]
    }
    assert set(schemas) == {
        "search_filings",
        "read_chunk",
        "read_surrounding_chunks",
        "submit_answer",
    }
    assert "client" not in schemas["search_filings"]["parameters"]["properties"]
    assert schemas["submit_answer"]["strict"] is True
    assert mock_openai.requests[0]["reasoning_effort"] == "low"
    assert "temperature" not in mock_openai.requests[0]


@pytest.mark.anyio
async def test_graph_retries_bad_citations_with_validation_feedback(
    mock_openai, model_completion, model_tool_call
):
    deps = _deps(mock_openai.client, retrieved=True)
    mock_openai.responses.extend(
        [
            model_completion(
                tool_calls=[
                    model_tool_call(
                        "submit_answer", _answer(excerpt="Revenue fell by 90%.")
                    )
                ]
            ),
            model_completion(tool_calls=[model_tool_call("submit_answer", _answer())]),
        ]
    )

    result = await document_agent.ainvoke(
        {"messages": [{"role": "user", "content": "How did revenue change?"}]},
        context=deps,
        config=graph_config(),
    )

    validate_grounded_answer(result["grounded_answer"], deps.registry)
    assert len(mock_openai.requests) == 2
    feedback = mock_openai.requests[1]["messages"][-1]
    assert feedback["role"] == "tool"
    assert "excerpt is not from the retrieved passage text" in feedback["content"]


@pytest.mark.anyio
@pytest.mark.parametrize("bad_output", ["not JSON", {"answer": ""}])
async def test_graph_retries_invalid_output_schema(
    mock_openai, model_completion, model_tool_call, bad_output
):
    mock_openai.responses.extend(
        [
            model_completion(tool_calls=[model_tool_call("submit_answer", bad_output)]),
            model_completion(
                tool_calls=[model_tool_call("submit_answer", _insufficient())]
            ),
        ]
    )

    result = await document_agent.ainvoke(
        {"messages": [{"role": "user", "content": "Missing filing fact?"}]},
        context=_deps(mock_openai.client),
        config=graph_config(),
    )

    assert result["grounded_answer"].insufficient_evidence is True
    assert len(mock_openai.requests) == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "message",
    [{"content": "Please clarify."}, {"content": None, "refusal": "I cannot answer."}],
)
async def test_graph_requires_structured_output_after_a_plain_response_or_refusal(
    mock_openai, model_completion, model_tool_call, message
):
    mock_openai.responses.extend(
        [
            model_completion(**message),
            model_completion(
                tool_calls=[model_tool_call("submit_answer", _insufficient())]
            ),
        ]
    )

    result = await document_agent.ainvoke(
        {"messages": [{"role": "user", "content": "Missing filing fact?"}]},
        context=_deps(mock_openai.client),
        config=graph_config(),
    )

    assert result["grounded_answer"].insufficient_evidence
    retry_messages = mock_openai.requests[1]["messages"]
    assert retry_messages[-2]["content"] == (
        message.get("content") or message.get("refusal")
    )
    assert retry_messages[-1]["role"] == "user"
    assert "Call submit_answer exactly once" in retry_messages[-1]["content"]


@pytest.mark.anyio
async def test_graph_rejects_citations_to_chunks_not_retrieved_this_turn(
    mock_openai, model_completion, model_tool_call
):
    mock_openai.responses.extend(
        [
            model_completion(tool_calls=[model_tool_call("submit_answer", _answer())])
            for _ in range(settings.agent_output_retries + 1)
        ]
    )
    deps = _deps(mock_openai.client)

    with pytest.raises(GroundingError, match="was not retrieved in this turn"):
        await document_agent.ainvoke(
            {"messages": [{"role": "user", "content": "Repeat the previous answer."}]},
            context=deps,
            config=graph_config(),
        )

    assert len(mock_openai.requests) == settings.agent_output_retries + 1
    assert deps.registry.passages == {}


@pytest.mark.anyio
async def test_graph_request_limit_survives_more_than_default_graph_recursion(
    mock_openai, model_completion, model_tool_call, monkeypatch
):
    monkeypatch.setattr(settings, "agent_max_requests", 20)
    monkeypatch.setattr(settings, "agent_max_tool_calls", 30)
    deps = _deps(mock_openai.client)
    deps.retriever.search.return_value = []
    mock_openai.responses.extend(
        [
            model_completion(
                tool_calls=[
                    model_tool_call("search_filings", {"query": "missing fact"})
                ]
            )
            for _ in range(20)
        ]
    )

    with pytest.raises(AgentLimitError, match="Maximum model requests"):
        await document_agent.ainvoke(
            {"messages": [{"role": "user", "content": "Find a missing fact."}]},
            context=deps,
            config=graph_config(),
        )

    assert len(mock_openai.requests) == 20
    assert deps.retriever.search.await_count == 20


@pytest.mark.anyio
async def test_graph_checks_the_entire_tool_batch_before_running_it(
    mock_openai, model_completion, model_tool_call, monkeypatch
):
    monkeypatch.setattr(settings, "agent_max_tool_calls", 1)
    deps = _deps(mock_openai.client)
    mock_openai.responses.append(
        model_completion(
            tool_calls=[
                model_tool_call("search_filings", {"query": "first fact"}, "call-1"),
                model_tool_call("search_filings", {"query": "second fact"}, "call-2"),
            ]
        )
    )

    with pytest.raises(AgentLimitError, match="Maximum retrieval tool calls"):
        await document_agent.ainvoke(
            {"messages": [{"role": "user", "content": "Compare facts."}]},
            context=deps,
            config=graph_config(),
        )

    deps.retriever.search.assert_not_awaited()
    assert len(mock_openai.requests) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "args", "feedback"),
    [
        ("read_chunk", {"chunk_id": "bad-uuid"}, "UUID"),
        ("unknown_tool", {}, "Unknown retrieval tool"),
    ],
)
async def test_graph_reports_invalid_tools_without_executing_retrieval(
    mock_openai, model_completion, model_tool_call, name, args, feedback
):
    deps = _deps(mock_openai.client)
    mock_openai.responses.extend(
        [
            model_completion(tool_calls=[model_tool_call(name, args)]),
            model_completion(
                tool_calls=[model_tool_call("submit_answer", _insufficient())]
            ),
        ]
    )

    result = await document_agent.ainvoke(
        {"messages": [{"role": "user", "content": "Read a filing."}]},
        context=deps,
        config=graph_config(),
    )

    assert result["grounded_answer"].insufficient_evidence
    assert feedback in mock_openai.requests[1]["messages"][-1]["content"]
    deps.retriever.get_chunk.assert_not_awaited()
    assert deps.registry.passages == {}


@pytest.mark.anyio
async def test_graph_can_explain_insufficient_evidence_with_zero_tool_budget(
    mock_openai, model_completion, model_tool_call, monkeypatch
):
    monkeypatch.setattr(settings, "agent_max_tool_calls", 0)
    monkeypatch.setattr(settings, "openai_chat_model", "gpt-4.1-mini")
    mock_openai.responses.append(
        model_completion(tool_calls=[model_tool_call("submit_answer", _insufficient())])
    )

    result = await document_agent.ainvoke(
        {"messages": [{"role": "user", "content": "Which stock should I buy?"}]},
        context=_deps(mock_openai.client),
        config=graph_config(),
    )

    assert result["grounded_answer"].citations == []
    assert mock_openai.requests[0]["temperature"] == settings.agent_temperature
    assert "reasoning_effort" not in mock_openai.requests[0]


@pytest.mark.anyio
async def test_graph_retrieves_before_validating_an_answer_in_the_same_batch(
    mock_openai, model_completion, model_tool_call
):
    deps = _deps(mock_openai.client)
    deps.retriever.get_chunk.return_value = _passage()
    mock_openai.responses.extend(
        [
            model_completion(
                tool_calls=[
                    model_tool_call(
                        "submit_answer",
                        _answer(excerpt="Invented revenue claim."),
                        "answer-1",
                    ),
                    model_tool_call(
                        "read_chunk", {"chunk_id": str(CHUNK_ID)}, "read-1"
                    ),
                ]
            ),
            model_completion(
                tool_calls=[model_tool_call("submit_answer", _answer(), "answer-2")]
            ),
        ]
    )

    result = await document_agent.ainvoke(
        {
            "messages": [
                {"role": "user", "content": "Check the passage from our last turn."}
            ]
        },
        context=deps,
        config=graph_config(),
    )

    validate_grounded_answer(result["grounded_answer"], deps.registry)
    deps.retriever.get_chunk.assert_awaited_once_with(CHUNK_ID)
    replies = mock_openai.requests[1]["messages"][-2:]
    assert {reply["tool_call_id"] for reply in replies} == {"read-1", "answer-1"}
    assert "excerpt is not from the retrieved passage text" in replies[-1]["content"]
