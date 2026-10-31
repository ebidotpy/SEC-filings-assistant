from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from app.assistant.deps import RetrievalRegistry
from app.assistant.outputs import Citation, GroundedAnswer
from app.grounding.validator import GroundingError, validate_grounded_answer
from app.retrieval.types import SourcePassage

CHUNK_A = UUID("00000000-0000-0000-0000-000000000001")
CHUNK_B = UUID("00000000-0000-0000-0000-000000000002")


def _passage(chunk_id: UUID, text: str) -> SourcePassage:
    return SourcePassage(
        chunk_id=chunk_id,
        document_id=UUID("00000000-0000-0000-0000-000000000010"),
        chunk_index=0,
        text=text,
        ticker="AAPL",
        company_name="Apple Inc.",
        form="10-K",
        filing_date=date(2024, 10, 31),
        accession_number="0000320193-24-000123",
        page="42",
        section="Item 7",
    )


def _registry(*passages: SourcePassage) -> RetrievalRegistry:
    registry = RetrievalRegistry()
    registry.register_many(list(passages))
    return registry


def test_validate_grounded_answer_happy_path():
    passage = _passage(CHUNK_A, "iPhone revenue increased year over year.")
    answer = GroundedAnswer(
        answer="iPhone revenue increased year over year. [1]",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_A,
                excerpt="iPhone revenue increased year over year.",
            )
        ],
    )

    validate_grounded_answer(answer, _registry(passage))


def test_validate_grounded_answer_insufficient_evidence():
    answer = GroundedAnswer(
        answer="The corpus does not contain enough evidence to answer.",
        citations=[],
        insufficient_evidence=True,
    )

    validate_grounded_answer(answer, RetrievalRegistry())


def test_validate_grounded_answer_rejects_citations_with_insufficient_evidence():
    answer = GroundedAnswer(
        answer="Not enough evidence.",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_A,
                excerpt="some text",
            )
        ],
        insufficient_evidence=True,
    )

    with pytest.raises(GroundingError, match="must not include citations"):
        validate_grounded_answer(answer, _registry(_passage(CHUNK_A, "some text")))


def test_validate_grounded_answer_rejects_unretrieved_chunk():
    answer = GroundedAnswer(
        answer="Claim [1]",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_B,
                excerpt="Claim",
            )
        ],
    )

    with pytest.raises(GroundingError, match="was not retrieved"):
        validate_grounded_answer(answer, _registry(_passage(CHUNK_A, "Claim")))


def test_validate_grounded_answer_rejects_excerpt_mismatch():
    passage = _passage(CHUNK_A, "Services revenue grew steadily.")
    answer = GroundedAnswer(
        answer="Services revenue grew. [1]",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_A,
                excerpt="Hardware revenue grew steadily.",
            )
        ],
    )

    with pytest.raises(GroundingError, match="excerpt is not from"):
        validate_grounded_answer(answer, _registry(passage))


def test_validate_grounded_answer_folds_curly_quotes_and_dashes():
    passage = _passage(
        CHUNK_A,
        "The Company\u2019s iPhone net sales decreased 2% \u2014 or $4.9 billion.",
    )
    answer = GroundedAnswer(
        answer="iPhone net sales fell. [1]",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_A,
                excerpt="The Company's iPhone net sales decreased 2% - or $4.9 billion.",
            )
        ],
    )

    validate_grounded_answer(answer, _registry(passage))


def test_validate_grounded_answer_rejects_non_contiguous_excerpt():
    passage = _passage(
        CHUNK_A,
        "(2) Services net sales include amortization.\n"
        "iPhone\n"
        "iPhone net sales decreased 2% or $4.9 billion during 2023.",
    )
    answer = GroundedAnswer(
        answer="iPhone net sales fell. [1]",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_A,
                excerpt=(
                    "(2) Services net sales include amortization.\n"
                    "iPhone net sales decreased 2% or $4.9 billion during 2023."
                ),
            )
        ],
    )

    with pytest.raises(GroundingError, match="excerpt is not from"):
        validate_grounded_answer(answer, _registry(passage))


def test_validate_grounded_answer_rejects_excerpt_from_wrong_chunk():
    passage_a = _passage(CHUNK_A, "(2) Services net sales include amortization.")
    passage_b = _passage(
        CHUNK_B,
        "iPhone net sales decreased 2% or $4.9 billion during 2023.",
    )
    answer = GroundedAnswer(
        answer="iPhone net sales fell. [1]",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_A,
                excerpt="iPhone net sales decreased 2% or $4.9 billion during 2023.",
            )
        ],
    )

    with pytest.raises(GroundingError, match="excerpt is not from"):
        validate_grounded_answer(answer, _registry(passage_a, passage_b))


def test_validate_grounded_answer_rejects_missing_markers():
    passage = _passage(CHUNK_A, "Mac revenue declined.")
    answer = GroundedAnswer(
        answer="Mac revenue declined.",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_A,
                excerpt="Mac revenue declined.",
            )
        ],
    )

    with pytest.raises(GroundingError, match="inline citation markers"):
        validate_grounded_answer(answer, _registry(passage))


def test_validate_grounded_answer_rejects_orphan_marker():
    passage = _passage(CHUNK_A, "Wearables revenue was flat.")
    answer = GroundedAnswer(
        answer="Wearables revenue was flat. [1] [2]",
        citations=[
            Citation(
                citation_index=1,
                chunk_id=CHUNK_A,
                excerpt="Wearables revenue was flat.",
            )
        ],
    )

    with pytest.raises(GroundingError, match="without citations"):
        validate_grounded_answer(answer, _registry(passage))
