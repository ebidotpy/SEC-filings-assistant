from __future__ import annotations

import re
import unicodedata

from app.assistant.deps import RetrievalRegistry
from app.assistant.outputs import GroundedAnswer

_CITATION_MARKER = re.compile(r"\[(\d+)\]")

# Fold typographic variants that models routinely emit in place of the source
# characters, so excerpt matching does not fail on non-semantic differences.
_CHAR_FOLDING = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)


class GroundingError(Exception):
    """Raised when a grounded answer violates the citation contract."""


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).translate(_CHAR_FOLDING)
    return " ".join(normalized.split())


def validate_grounded_answer(
    answer: GroundedAnswer,
    registry: RetrievalRegistry,
) -> None:
    if not answer.answer.strip():
        raise GroundingError("Answer text is empty")

    if answer.insufficient_evidence:
        if answer.citations:
            raise GroundingError(
                "Insufficient-evidence answers must not include citations"
            )
        return

    if not answer.citations:
        raise GroundingError("Grounded answers must include at least one citation")

    seen_indexes: set[int] = set()
    for citation in answer.citations:
        if citation.citation_index in seen_indexes:
            raise GroundingError(
                f"Duplicate citation index [{citation.citation_index}]"
            )
        seen_indexes.add(citation.citation_index)

        passage = registry.passages.get(citation.chunk_id)
        if passage is None:
            raise GroundingError(
                f"Citation [{citation.citation_index}] references chunk "
                f"{citation.chunk_id} that was not retrieved in this turn"
            )

        normalized_excerpt = _normalize(citation.excerpt)
        normalized_passage = _normalize(passage.text)
        if normalized_excerpt not in normalized_passage:
            raise GroundingError(
                f"Citation [{citation.citation_index}] excerpt is not from the "
                "retrieved passage text"
            )

    markers = {int(match) for match in _CITATION_MARKER.findall(answer.answer)}
    if not markers:
        raise GroundingError("Answer must include inline citation markers like [1]")

    citation_indexes = {citation.citation_index for citation in answer.citations}
    unreferenced = citation_indexes - markers
    if unreferenced:
        missing = ", ".join(f"[{index}]" for index in sorted(unreferenced))
        raise GroundingError(f"Citation indexes not referenced in answer: {missing}")

    orphan_markers = markers - citation_indexes
    if orphan_markers:
        missing = ", ".join(f"[{index}]" for index in sorted(orphan_markers))
        raise GroundingError(f"Answer markers without citations: {missing}")
