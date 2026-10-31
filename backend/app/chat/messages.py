from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.assistant.outputs import Citation, GroundedAnswer
from app.database.chats import CitationInsert, CitationRow, MessageRow
from app.retrieval.types import SourcePassage


class UIMessagePart(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    text: str | None = None


class UIMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    parts: list[UIMessagePart]


class StreamChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: UUID = Field(alias="threadId")
    messages: list[UIMessage]


def extract_text(message: UIMessage) -> str:
    parts: list[str] = []
    for part in message.parts:
        if part.type == "text" and part.text:
            parts.append(part.text)
    return "".join(parts)


def latest_user_message(messages: list[UIMessage]) -> UIMessage | None:
    for message in reversed(messages):
        if message.role == "user":
            return message
    return None


def prior_messages(
    messages: list[UIMessage], current_user_message: UIMessage
) -> list[UIMessage]:
    return [message for message in messages if message.id != current_user_message.id]


def to_model_history(messages: list[UIMessage]) -> list[ModelMessage]:
    history: list[ModelMessage] = []
    for message in messages:
        text = extract_text(message).strip()
        if not text:
            continue
        if message.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(text)]))
        elif message.role == "assistant":
            history.append(ModelResponse(parts=[TextPart(text)]))
    return history


def citation_payload(citation: Citation, passage: SourcePassage) -> dict[str, Any]:
    return {
        "citationIndex": citation.citation_index,
        "chunkId": str(citation.chunk_id),
        "excerpt": citation.excerpt,
        "ticker": passage.ticker,
        "companyName": passage.company_name,
        "form": passage.form,
        "filingDate": passage.filing_date.isoformat(),
        "page": passage.page,
        "section": passage.section,
        "accessionNumber": passage.accession_number,
    }


def citation_payload_from_row(row: CitationRow) -> dict[str, Any]:
    return {
        "citationIndex": row.citation_index,
        "chunkId": str(row.chunk_id),
        "excerpt": row.excerpt,
        "ticker": row.ticker,
        "companyName": row.company_name,
        "form": row.form,
        "filingDate": row.filing_date.isoformat(),
        "page": row.page,
        "section": row.section,
    }


def assistant_parts(
    answer_text: str,
    citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": answer_text}]
    if citations:
        parts.append({"type": "data-citations", "data": {"citations": citations}})
    return parts


def ui_message_from_row(row: MessageRow) -> dict[str, Any]:
    if row.parts:
        parts = list(row.parts)
    elif row.content:
        parts = [{"type": "text", "text": row.content}]
    else:
        parts = []

    if row.role == "assistant" and row.citations:
        has_citation_part = any(part.get("type") == "data-citations" for part in parts)
        if not has_citation_part:
            parts.append(
                {
                    "type": "data-citations",
                    "data": {
                        "citations": [
                            citation_payload_from_row(citation)
                            for citation in row.citations
                        ]
                    },
                }
            )

    return {
        "id": str(row.id),
        "role": row.role,
        "parts": parts,
    }


def text_parts(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]


def truncate_title(text: str, max_length: int = 50) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 1].rstrip() + "…"


def build_citation_inserts(
    grounded: GroundedAnswer,
    passages: dict[UUID, SourcePassage],
) -> list[CitationInsert]:
    inserts: list[CitationInsert] = []
    for citation in grounded.citations:
        passage = passages[citation.chunk_id]
        inserts.append(
            CitationInsert(
                citation_index=citation.citation_index,
                chunk_id=citation.chunk_id,
                excerpt=citation.excerpt,
                ticker=passage.ticker,
                company_name=passage.company_name,
                form=passage.form,
                filing_date=passage.filing_date,
                page=passage.page,
                section=passage.section,
            )
        )
    return inserts
