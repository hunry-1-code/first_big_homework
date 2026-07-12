from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class AggregationConfig:
    attach_threshold: float = 0.72
    create_threshold: float = 0.58
    move_margin: float = 0.15
    bge_weight: float = 0.45
    tfidf_weight: float = 0.25
    entity_weight: float = 0.20
    time_weight: float = 0.10
    candidate_limit: int = 20
    maximum_event_gap_days: int = 30
    minimum_evidence_count: int = 1
    search_cache_hours: int = 24
    related_event_limit: int = 5
    algorithm_version: str = "event-aggregation-v1"

    def __post_init__(self) -> None:
        if not 0 <= self.create_threshold < self.attach_threshold <= 1:
            raise ValueError("事件创建阈值必须小于加入阈值，且都在 0～1")
        if not 0 <= self.move_margin <= 1:
            raise ValueError("事件移动分差必须在 0～1")
        weights = (
            self.bge_weight,
            self.tfidf_weight,
            self.entity_weight,
            self.time_weight,
        )
        if any(value < 0 for value in weights) or sum(weights) <= 0:
            raise ValueError("事件聚合权重必须非负且总和大于零")
        if self.candidate_limit < 1 or self.minimum_evidence_count < 1:
            raise ValueError("候选数量和最低证据数必须为正整数")
        if self.search_cache_hours < 1 or self.related_event_limit < 1:
            raise ValueError("缓存时间和相似事件数量必须为正整数")

    def as_dict(self) -> dict:
        return asdict(self)

    def config_hash(self) -> str:
        payload = json.dumps(
            self.as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["AggregationConfig"]
