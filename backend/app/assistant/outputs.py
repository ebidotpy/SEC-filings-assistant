from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class Citation(BaseModel):
    citation_index: int = Field(ge=1)
    chunk_id: UUID
    excerpt: str = Field(min_length=1)


class GroundedAnswer(BaseModel):
    answer: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    insufficient_evidence: bool = False
