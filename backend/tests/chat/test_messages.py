from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from app.assistant.outputs import Citation, GroundedAnswer
from app.chat.messages import (
    UIMessage,
    UIMessagePart,
    assistant_parts,
    prior_messages,
    to_model_history,
    ui_message_from_row,
)
from app.database.chats import CitationRow, MessageRow
from pydantic_ai.messages import ModelRequest, ModelResponse


def test_to_model_history_converts_user_and_assistant_messages():
    messages = [
        UIMessage(
            id="1",
            role="user",
            parts=[UIMessagePart(type="text", text="What changed in AWS margins?")],
        ),
        UIMessage(
            id="2",
            role="assistant",
            parts=[UIMessagePart(type="text", text="AWS margins improved. [1]")],
        ),
        UIMessage(
            id="3",
            role="user",
            parts=[UIMessagePart(type="text", text="Compare 2023 and 2024.")],
        ),
    ]

    history = to_model_history(messages[:-1])

    assert len(history) == 2
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[1], ModelResponse)


def test_prior_messages_excludes_current_user_message():
    current = UIMessage(
        id="3",
        role="user",
        parts=[UIMessagePart(type="text", text="Latest question")],
    )
    messages = [
        UIMessage(
            id="1", role="user", parts=[UIMessagePart(type="text", text="Earlier")]
        ),
        UIMessage(
            id="2",
            role="assistant",
            parts=[UIMessagePart(type="text", text="Earlier answer")],
        ),
        current,
    ]

    assert len(prior_messages(messages, current)) == 2


def test_assistant_parts_includes_citation_data_part():
    grounded = GroundedAnswer(
        answer="Revenue mix shifted toward Services. [1]",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=UUID("00000000-0000-0000-0000-000000000001"),
                excerpt="Services revenue increased.",
            )
        ],
    )
    citation_payloads = [
        {
            "citationIndex": 1,
            "chunkId": "00000000-0000-0000-0000-000000000001",
            "excerpt": "Services revenue increased.",
            "ticker": "AAPL",
        }
    ]

    parts = assistant_parts(grounded.answer, citation_payloads)

    assert parts[0]["type"] == "text"
    assert parts[1]["type"] == "data-citations"
    assert parts[1]["data"]["citations"][0]["ticker"] == "AAPL"


def test_ui_message_from_row_hydrates_citations_when_missing_from_parts():
    message_id = UUID("00000000-0000-0000-0000-000000000020")
    row = MessageRow(
        id=message_id,
        thread_id=UUID("00000000-0000-0000-0000-000000000030"),
        role="assistant",
        content="Answer text [1]",
        parts=[{"type": "text", "text": "Answer text [1]"}],
        sequence=2,
        created_at=datetime(2024, 10, 31, 12, 0, 0),
        citations=[
            CitationRow(
                id=UUID("00000000-0000-0000-0000-000000000040"),
                message_id=message_id,
                chunk_id=UUID("00000000-0000-0000-0000-000000000001"),
                citation_index=1,
                excerpt="Answer excerpt",
                ticker="AAPL",
                company_name="Apple Inc.",
                form="10-K",
                filing_date=date(2024, 10, 31),
                page="12",
                section="MD&A",
            )
        ],
    )

    ui_message = ui_message_from_row(row)

    assert len(ui_message["parts"]) == 2
    assert ui_message["parts"][1]["type"] == "data-citations"
    assert ui_message["parts"][1]["data"]["citations"][0]["citationIndex"] == 1
