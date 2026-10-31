from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database.models.chat_message import ChatMessage
from app.database.models.chat_thread import ChatThread
from app.database.models.message_citation import MessageCitation
from app.database.models.message_role import MessageRole
from app.database.session import get_db_session

DEFAULT_THREAD_TITLE = "New chat"


@dataclass(frozen=True, slots=True)
class ThreadRow:
    id: UUID
    user_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CitationRow:
    id: UUID
    message_id: UUID
    chunk_id: UUID
    citation_index: int
    excerpt: str
    ticker: str
    company_name: str | None
    form: str
    filing_date: date
    page: str | None
    section: str | None


@dataclass(frozen=True, slots=True)
class MessageRow:
    id: UUID
    thread_id: UUID
    role: str
    content: str | None
    parts: list[dict[str, Any]] | None
    sequence: int
    created_at: datetime
    citations: list[CitationRow] | None = None


@dataclass(frozen=True, slots=True)
class CitationInsert:
    citation_index: int
    chunk_id: UUID
    excerpt: str
    ticker: str
    company_name: str | None
    form: str
    filing_date: date
    page: str | None
    section: str | None


def _thread_row(t: ChatThread) -> ThreadRow:
    return ThreadRow(
        id=t.id,
        user_id=t.user_id,
        title=t.title,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _citation_row(c: MessageCitation) -> CitationRow:
    return CitationRow(
        id=c.id,
        message_id=c.message_id,
        chunk_id=c.chunk_id,
        citation_index=c.citation_index,
        excerpt=c.excerpt,
        ticker=c.ticker,
        company_name=c.company_name,
        form=c.form,
        filing_date=c.filing_date,
        page=c.page,
        section=c.section,
    )


async def list_threads(user_id: UUID) -> list[ThreadRow]:
    async with get_db_session() as session:
        stmt = (
            select(ChatThread)
            .where(ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.desc())
        )
        result = await session.execute(stmt)
        threads = result.scalars().all()
        return [_thread_row(t) for t in threads]


async def create_thread(user_id: UUID, title: str = DEFAULT_THREAD_TITLE) -> ThreadRow:
    async with get_db_session() as session:
        thread = ChatThread(
            id=uuid4(),
            user_id=user_id,
            title=title,
        )
        session.add(thread)
        await session.commit()
        await session.refresh(thread)
        return _thread_row(thread)


async def get_thread_raw(thread_id: UUID) -> ThreadRow | None:
    async with get_db_session() as session:
        stmt = select(ChatThread).where(ChatThread.id == thread_id)
        result = await session.execute(stmt)
        thread = result.scalar_one_or_none()
        if thread is None:
            return None
        return _thread_row(thread)


async def list_messages(thread_id: UUID) -> list[MessageRow]:
    async with get_db_session() as session:
        stmt = (
            select(ChatMessage)
            .options(selectinload(ChatMessage.citations))
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.sequence)
        )
        result = await session.execute(stmt)
        messages = result.scalars().all()
        return [
            MessageRow(
                id=m.id,
                thread_id=m.thread_id,
                role=m.role.value if isinstance(m.role, MessageRole) else str(m.role),
                content=m.content,
                parts=m.parts,
                sequence=m.sequence,
                created_at=m.created_at,
                citations=[
                    _citation_row(c)
                    for c in sorted(m.citations, key=lambda x: x.citation_index)
                ],
            )
            for m in messages
        ]


async def next_sequence(thread_id: UUID) -> int:
    async with get_db_session() as session:
        stmt = select(func.coalesce(func.max(ChatMessage.sequence), 0)).where(
            ChatMessage.thread_id == thread_id
        )
        result = await session.execute(stmt)
        max_seq = result.scalar_one()
        return int(max_seq) + 1


async def insert_message(
    thread_id: UUID,
    *,
    role: str,
    content: str | None,
    parts: list[dict[str, Any]] | None,
    sequence: int,
    message_id: UUID | None = None,
) -> MessageRow:
    role_enum = (
        MessageRole(role)
        if role in MessageRole._value2member_map_
        else MessageRole.USER
    )
    msg = ChatMessage(
        id=message_id or uuid4(),
        thread_id=thread_id,
        role=role_enum,
        content=content,
        parts=parts,
        sequence=sequence,
    )
    async with get_db_session() as session:
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return MessageRow(
            id=msg.id,
            thread_id=msg.thread_id,
            role=msg.role.value,
            content=msg.content,
            parts=msg.parts,
            sequence=msg.sequence,
            created_at=msg.created_at,
            citations=[],
        )


async def insert_citations(
    message_id: UUID,
    citations: list[CitationInsert],
) -> list[CitationRow]:
    if not citations:
        return []

    db_citations = [
        MessageCitation(
            id=uuid4(),
            message_id=message_id,
            chunk_id=c.chunk_id,
            citation_index=c.citation_index,
            excerpt=c.excerpt,
            ticker=c.ticker,
            company_name=c.company_name,
            form=c.form,
            filing_date=c.filing_date,
            page=c.page,
            section=c.section,
        )
        for c in citations
    ]
    async with get_db_session() as session:
        session.add_all(db_citations)
        await session.commit()
        for c in db_citations:
            await session.refresh(c)
        return [_citation_row(c) for c in db_citations]


async def touch_thread(thread_id: UUID, *, title: str | None = None) -> None:
    async with get_db_session() as session:
        stmt = select(ChatThread).where(ChatThread.id == thread_id)
        result = await session.execute(stmt)
        thread = result.scalar_one_or_none()
        if thread is not None:
            thread.updated_at = datetime.now(UTC)
            if title is not None:
                thread.title = title
            await session.commit()
