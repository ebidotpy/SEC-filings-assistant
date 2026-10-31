from __future__ import annotations

from uuid import UUID

from app.retrieval.fusion import reciprocal_rank_fusion

A = UUID("00000000-0000-0000-0000-000000000001")
B = UUID("00000000-0000-0000-0000-000000000002")
C = UUID("00000000-0000-0000-0000-000000000003")
D = UUID("00000000-0000-0000-0000-000000000004")


def test_reciprocal_rank_fusion_prefers_overlap():
    fused = reciprocal_rank_fusion([[C, B, A], [B, A, D]], k=60)
    assert [chunk_id for chunk_id, _ in fused] == [B, A, C, D]
    assert fused[0][1] > fused[1][1]


def test_reciprocal_rank_fusion_single_list():
    fused = reciprocal_rank_fusion([[A, B]], k=60)
    assert [chunk_id for chunk_id, _ in fused] == [A, B]
    assert fused[0][1] == 1 / 61


def test_reciprocal_rank_fusion_empty_lists():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
