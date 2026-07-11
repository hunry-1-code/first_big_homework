from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class HotspotConfig:
    algorithm_version: str = "hotspot-v1"
    window_days: int = 7
    max_topics: int = 12
    top_words: int = 20
    random_state: int = 42
    lda_max_iter: int = 100
    topic_diversity_min: float = 0.70
    small_topic_ratio_max: float = 0.20
    low_confidence_threshold: float = 0.45
    minimum_reports: int = 3
    minimum_platforms: int = 2
    recent_activity_hours: int = 24
    half_life_hours: int = 24
    core_weight: float = 0.70
    spread_weight: float = 0.30
    ranking_limit: int = 20
    formula_version: str = "v1"

    def __post_init__(self) -> None:
        if self.window_days < 1 or self.max_topics < 2 or self.top_words < 1:
            raise ValueError("热点窗口、主题数和关键词数必须为正数")
        if self.lda_max_iter < 1:
            raise ValueError("LDA 迭代次数必须为正数")
        for value, name in (
            (self.topic_diversity_min, "topic_diversity_min"),
            (self.small_topic_ratio_max, "small_topic_ratio_max"),
            (self.low_confidence_threshold, "low_confidence_threshold"),
            (self.core_weight, "core_weight"),
            (self.spread_weight, "spread_weight"),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} 必须在 0 到 1 之间")
        if abs((self.core_weight + self.spread_weight) - 1.0) > 1e-9:
            raise ValueError("核心热度与传播热度权重之和必须为 1")
        if self.minimum_reports < 1 or self.minimum_platforms < 1:
            raise ValueError("热点证据门槛必须为正数")
        if self.recent_activity_hours < 1 or self.half_life_hours < 1:
            raise ValueError("时间窗口必须为正数")
        if self.ranking_limit < 1:
            raise ValueError("榜单数量必须为正数")

    def as_dict(self) -> dict:
        return asdict(self)

    def config_hash(self) -> str:
        payload = json.dumps(
            self.as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
