from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    ticker: str | None = None
    fiscal_year: int | None = None
    form: str | None = None


class ChunkHit(BaseModel):
    chunk_id: UUID
    rank: int = Field(ge=1)
    score: float | None = None


class SourcePassage(BaseModel):
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    text: str
    ticker: str
    company_name: str | None
    form: str
    filing_date: date
    accession_number: str
    page: str | None = None
    section: str | None = None
    chunk_metadata: dict[str, Any] = Field(default_factory=dict)
    rrf_score: float | None = None
