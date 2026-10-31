from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import SourcePassage


@dataclass
class RetrievalRegistry:
    passages: dict[UUID, SourcePassage] = field(default_factory=dict)

    def register(self, passage: SourcePassage) -> None:
        self.passages[passage.chunk_id] = passage

    def register_many(self, passages: list[SourcePassage]) -> None:
        for passage in passages:
            self.register(passage)


@dataclass
class DocumentAgentDeps:
    retriever: DocumentRetriever
    registry: RetrievalRegistry
