from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from app.analysis.aggregation_config import AggregationConfig


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def cosine_similarity(first: Iterable[float] | None, second: Iterable[float] | None) -> float | None:
    if first is None or second is None:
        return None
    left = [float(value) for value in first]
    right = [float(value) for value in second]
    if not left or len(left) != len(right):
        return None
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return None
    raw = sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
    return _clamp(max(0.0, raw))


def set_similarity(first: Iterable[str] | None, second: Iterable[str] | None) -> float | None:
    left = {str(value).strip().casefold() for value in (first or []) if str(value).strip()}
    right = {str(value).strip().casefold() for value in (second or []) if str(value).strip()}
    if not left or not right:
        return None
    return len(left & right) / len(left | right)


def entity_similarity(
    first: dict[str, Iterable[str]] | None,
    second: dict[str, Iterable[str]] | None,
) -> float | None:
    scores = []
    for key in sorted(set(first or {}) | set(second or {})):
        score = set_similarity((first or {}).get(key), (second or {}).get(key))
        if score is not None:
            scores.append(score)
    return sum(scores) / len(scores) if scores else None


def hard_conflict_reasons(
    first: dict[str, Iterable[str]] | None,
    second: dict[str, Iterable[str]] | None,
) -> list[str]:
    reasons = []
    for key, code in (
        ("location", "LOCATION_CONFLICT"),
        ("case", "CASE_CONFLICT"),
        ("organization", "ORGANIZATION_CONFLICT"),
    ):
        left = {str(value).strip().casefold() for value in (first or {}).get(key, []) if str(value).strip()}
        right = {str(value).strip().casefold() for value in (second or {}).get(key, []) if str(value).strip()}
        if left and right and not left & right:
            reasons.append(code)
    return reasons


@dataclass(slots=True)
class SimilarityResult:
    component_scores: dict[str, float]
    normalized_weights: dict[str, float]
    final_score: float
    hard_conflict: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def keyword_overlap_score(
    doc_keywords: Iterable[str] | None,
    cluster_keywords: Iterable[str] | None,
) -> float | None:
    """关键词 Jaccard 重叠度，用于短内容语义不足时的信号增强。"""
    dk = {str(k).strip().casefold() for k in (doc_keywords or []) if str(k).strip()}
    ck = {str(k).strip().casefold() for k in (cluster_keywords or []) if str(k).strip()}
    if not dk or not ck:
        return None
    return len(dk & ck) / len(dk | ck)


def score_event_match(
    *,
    config: AggregationConfig,
    bge_similarity: float | None = None,
    tfidf_similarity: float | None = None,
    entity_similarity: float | None = None,
    time_compatibility: float | None = None,
    keyword_overlap: float | None = None,
    article_entities: dict[str, Iterable[str]] | None = None,
    candidate_entities: dict[str, Iterable[str]] | None = None,
) -> SimilarityResult:
    values = {
        "bge": bge_similarity,
        "tfidf": tfidf_similarity,
        "entity": entity_similarity,
        "time": time_compatibility,
        "keyword": keyword_overlap,
    }
    # 关键词重叠权重：短内容语义弱时提供信号补充
    KW_WEIGHT = 0.05
    base_weights = {
        "bge": config.bge_weight - KW_WEIGHT,
        "tfidf": config.tfidf_weight,
        "entity": config.entity_weight,
        "time": config.time_weight,
        "keyword": KW_WEIGHT,
    }
    available = {
        key: _clamp(value)
        for key, value in values.items()
        if value is not None and base_weights[key] > 0
    }
    total_weight = sum(base_weights[key] for key in available)
    normalized = (
        {key: base_weights[key] / total_weight for key in available}
        if total_weight
        else {}
    )
    final_score = sum(available[key] * normalized[key] for key in available)
    conflicts = hard_conflict_reasons(article_entities, candidate_entities)
    warnings = []
    if bge_similarity is None:
        warnings.append("BGE_UNAVAILABLE")
    if tfidf_similarity is None:
        warnings.append("TFIDF_UNAVAILABLE")
    return SimilarityResult(
        component_scores=available,
        normalized_weights=normalized,
        final_score=round(final_score, 6),
        hard_conflict=bool(conflicts),
        reasons=conflicts,
        warnings=warnings,
    )


__all__ = [
    "SimilarityResult",
    "cosine_similarity",
    "entity_similarity",
    "hard_conflict_reasons",
    "score_event_match",
    "set_similarity",
]
