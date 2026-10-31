"""Postgres access for document chunk retrieval (pgvector + full-text search)."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.database.session import get_db_engine
from app.retrieval.types import SearchFilters, SourcePassage

_PASSAGE_SELECT = """
    dc.id,
    dc.document_id,
    dc.chunk_index,
    dc.text,
    dc.page,
    dc.section,
    dc.chunk_metadata,
    sd.ticker,
    sd.company_name,
    sd.form,
    sd.filing_date,
    sd.accession_number
"""


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


def build_filter_clause(filters: SearchFilters | None) -> tuple[str, dict[str, Any]]:
    if filters is None:
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}

    if filters.ticker is not None:
        clauses.append("sd.ticker = :ticker")
        params["ticker"] = filters.ticker.upper()
    if filters.fiscal_year is not None:
        clauses.append("sd.fiscal_year = :fiscal_year")
        params["fiscal_year"] = filters.fiscal_year
    if filters.form is not None:
        clauses.append("sd.form = :form")
        params["form"] = filters.form.upper()

    if not clauses:
        return "", {}

    return " AND " + " AND ".join(clauses), params


def _row_to_passage(row: Any, *, rrf_score: float | None = None) -> SourcePassage:
    return SourcePassage(
        chunk_id=row.id,
        document_id=row.document_id,
        chunk_index=row.chunk_index,
        text=row.text,
        ticker=row.ticker,
        company_name=row.company_name,
        form=row.form,
        filing_date=row.filing_date
        if isinstance(row.filing_date, date)
        else date.fromisoformat(str(row.filing_date)),
        accession_number=row.accession_number,
        page=row.page,
        section=row.section,
        chunk_metadata=dict(row.chunk_metadata or {}),
        rrf_score=rrf_score,
    )


async def semantic_search_chunk_ids(
    embedding: list[float],
    *,
    limit: int,
    filters: SearchFilters | None = None,
    min_similarity: float = 0.0,
) -> list[UUID]:
    filter_sql, filter_params = build_filter_clause(filters)
    sql = f"""
        SELECT dc.id
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.document_id
        WHERE dc.embedding IS NOT NULL
          AND (1 - (dc.embedding <=> CAST(:embedding AS vector))) >= :min_similarity
          {filter_sql}
        ORDER BY dc.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """
    params = {
        "embedding": vector_literal(embedding),
        "min_similarity": min_similarity,
        "limit": limit,
        **filter_params,
    }
    engine = get_db_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(sql), params)
        return [row.id for row in result.fetchall()]


async def fulltext_search_chunk_ids(
    query: str,
    *,
    limit: int,
    filters: SearchFilters | None = None,
) -> list[UUID]:
    filter_sql, filter_params = build_filter_clause(filters)
    sql = f"""
        SELECT dc.id
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.document_id,
             plainto_tsquery('english', :query_text) AS query
        WHERE dc.search_vector @@ query
          {filter_sql}
        ORDER BY ts_rank_cd(dc.search_vector, query) DESC
        LIMIT :limit
    """
    params = {"query_text": query, "limit": limit, **filter_params}
    engine = get_db_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(sql), params)
        return [row.id for row in result.fetchall()]


async def fetch_passages_by_ids(
    chunk_ids: list[UUID],
    *,
    rrf_scores: dict[UUID, float] | None = None,
) -> list[SourcePassage]:
    if not chunk_ids:
        return []

    sql = f"""
        SELECT {_PASSAGE_SELECT.strip()}
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.document_id
        WHERE dc.id = ANY(CAST(:chunk_ids AS uuid[]))
    """
    engine = get_db_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(sql),
            {"chunk_ids": [str(chunk_id) for chunk_id in chunk_ids]},
        )
        rows = {row.id: row for row in result.fetchall()}

    passages: list[SourcePassage] = []
    for chunk_id in chunk_ids:
        row = rows.get(chunk_id)
        if row is None:
            continue
        score = rrf_scores.get(chunk_id) if rrf_scores else None
        passages.append(_row_to_passage(row, rrf_score=score))
    return passages


async def fetch_passage_by_id(chunk_id: UUID) -> SourcePassage | None:
    passages = await fetch_passages_by_ids([chunk_id])
    return passages[0] if passages else None


async def fetch_neighbor_chunk_ids(
    document_id: UUID,
    chunk_index: int,
    *,
    radius: int,
) -> list[UUID]:
    if radius < 1:
        return []

    sql = """
        SELECT id
        FROM document_chunks
        WHERE document_id = :document_id
          AND chunk_index BETWEEN :min_index AND :max_index
          AND chunk_index <> :chunk_index
        ORDER BY chunk_index
    """
    engine = get_db_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(sql),
            {
                "document_id": str(document_id),
                "min_index": chunk_index - radius,
                "max_index": chunk_index + radius,
                "chunk_index": chunk_index,
            },
        )
        return [row.id for row in result.fetchall()]
