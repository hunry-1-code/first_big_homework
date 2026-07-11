from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class SentimentConfig:
    text_limit: int = 500
    neutral_score_min: float = -0.20
    neutral_score_max: float = 0.20
    llm_max_concurrency: int = 3
    llm_retry_count: int = 3
    minimum_success_ratio: float = 0.80
    platform_min_articles: int = 3
    platform_min_representatives: int = 2
    snownlp_positive_threshold: float = 0.60
    snownlp_negative_threshold: float = 0.40
    snownlp_confidence_cap: float = 0.75
    algorithm_version: str = "sentiment-v1"
    prompt_version: str = "sentiment-prompt-v1"
    preprocess_version: str = "sentiment-text-v1"

    def __post_init__(self) -> None:
        if self.text_limit < 1:
            raise ValueError("情感分析文本长度必须为正整数")
        if not -1 <= self.neutral_score_min <= self.neutral_score_max <= 1:
            raise ValueError("中性分数区间必须位于 -1～1 且顺序正确")
        if self.llm_max_concurrency < 1 or self.llm_retry_count < 0:
            raise ValueError("LLM 并发数必须为正数，重试次数不能为负")
        if not 0 < self.minimum_success_ratio <= 1:
            raise ValueError("最低成功比例必须位于 0～1")
        if self.platform_min_articles < 1 or self.platform_min_representatives < 1:
            raise ValueError("平台样本门槛必须为正整数")
        if not 0 <= self.snownlp_negative_threshold < self.snownlp_positive_threshold <= 1:
            raise ValueError("SnowNLP 负面阈值必须小于正面阈值")
        if not 0 <= self.snownlp_confidence_cap <= 1:
            raise ValueError("SnowNLP 置信度上限必须位于 0～1")

    def as_dict(self) -> dict:
        return asdict(self)

    def config_hash(self) -> str:
        payload = json.dumps(
            self.as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["SentimentConfig"]
