from dataclasses import asdict, dataclass

from app.propagation.evidence import (
    author_matches,
    keyword_or_entity_terms,
    source_evidence,
    tokens,
)


MIN_SEMANTIC_SCORE = 0.20
MIN_INFERRED_SCORE = 0.38


def _set_similarity(first, second) -> float:
    return len(first & second) / len(first | second) if first and second else 0.0


def similarity(first, second) -> float:
    return _set_similarity(tokens(first), tokens(second))


@dataclass(frozen=True, slots=True)
class InferredEvidence:
    semantic: float
    time: float
    source: float
    entity_or_keyword: float
    cross_platform: float
    final_score: float
    reasons: tuple[str, ...]

    @property
    def eligible(self) -> bool:
        return (
            self.semantic >= MIN_SEMANTIC_SCORE
            and (self.source > 0 or self.entity_or_keyword > 0)
            and self.final_score >= MIN_INFERRED_SCORE
        )

    def components(self) -> dict:
        payload = asdict(self)
        payload.pop("reasons", None)
        return payload


def inferred_score(parent, child) -> InferredEvidence:
    semantic = similarity(parent, child)
    pt = getattr(parent, "publish_time", None) or getattr(parent, "first_crawled_at", None)
    ct = getattr(child, "publish_time", None) or getattr(child, "first_crawled_at", None)
    hours = max(0.0, (ct - pt).total_seconds() / 3600) if pt and ct else 168.0
    time_score = max(0.0, 1.0 - hours / (24 * 7))

    sources = source_evidence(child)
    source_score = 1.0 if any(author_matches(getattr(parent, "author", ""), value) for value in sources) else 0.0
    entity_or_keyword = _set_similarity(
        keyword_or_entity_terms(parent),
        keyword_or_entity_terms(child),
    )
    cross_platform = (
        1.0
        if getattr(parent, "platform", None) != getattr(child, "platform", None)
        else 0.0
    )
    final_score = (
        0.70 * semantic
        + 0.15 * time_score
        + 0.03 * source_score
        + 0.10 * entity_or_keyword
        + 0.02 * cross_platform
    )

    reasons = []
    if semantic >= MIN_SEMANTIC_SCORE:
        reasons.append(f"语义相似度 {semantic:.2f}")
    if source_score:
        reasons.append("正文包含可匹配的来源作者")
    if entity_or_keyword:
        reasons.append(f"共享关键词或实体 {entity_or_keyword:.2f}")
    if cross_platform:
        reasons.append("跨平台后续报道")
    return InferredEvidence(
        semantic=round(semantic, 6),
        time=round(time_score, 6),
        source=round(source_score, 6),
        entity_or_keyword=round(entity_or_keyword, 6),
        cross_platform=round(cross_platform, 6),
        final_score=round(final_score, 6),
        reasons=tuple(reasons),
    )


__all__ = [
    "InferredEvidence",
    "MIN_INFERRED_SCORE",
    "MIN_SEMANTIC_SCORE",
    "inferred_score",
    "similarity",
]
