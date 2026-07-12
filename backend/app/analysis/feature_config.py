from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    max_features: int = 5000
    ngram_range: tuple[int, int] = (1, 2)
    min_df: int = 1
    max_df: float = 0.90
    sublinear_tf: bool = True
    smooth_idf: bool = True
    title_weight: float = 1.0
    body_weight: float = 1.0
    article_keyword_limit: int = 10
    event_keyword_limit: int = 20
    minimum_normal_documents: int = 5
    algorithm_version: str = "content-analysis-v1"

    def as_dict(self) -> dict:
        data = asdict(self)
        data["ngram_range"] = list(self.ngram_range)
        return data

    def config_hash(self) -> str:
        payload = json.dumps(
            self.as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

