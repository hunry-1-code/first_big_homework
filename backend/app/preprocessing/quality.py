from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.preprocessing.result import StageResult


QUALITY_VERSION = "v1"
LENGTH_RULES = {
    "news": (80, 200),
    "social": (10, 30),
    "hotlist": (5, 10),
    "comment": (5, 15),
    "rss": (40, 120),
    "sample": (5, 30),
}
ADVERTISEMENT_PATTERNS = {
    "contact": re.compile(r"加(?:微信|vx)|私信|联系电话|扫码", re.IGNORECASE),
    "purchase": re.compile(r"购买|下单|优惠|代理|招商|返现|限时", re.IGNORECASE),
    "guarantee": re.compile(r"包治|稳赚|百分百|绝对有效", re.IGNORECASE),
}


def _valid_ratio(text: str) -> float:
    effective = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))
    return min(1.0, effective / max(1, len(text)))


def _repetition_score(text: str) -> float:
    tokens = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", text.lower())
    if len(tokens) < 4:
        return 0.5
    counts = Counter(tokens)
    dominant = max(counts.values()) / len(tokens)
    return max(0.0, min(1.0, 1.0 - dominant))


def evaluate_quality(
    text: str,
    source_type: str,
    metadata: dict[str, Any],
    extraction_method: str,
    extraction_degraded: bool,
    cleaning_statistics: dict[str, int] | None = None,
) -> StageResult:
    minimum, ideal = LENGTH_RULES.get(source_type, LENGTH_RULES["news"])
    effective_length = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text or ""))
    length_score = min(1.0, effective_length / ideal)
    valid_score = _valid_ratio(text or "")
    statistics = cleaning_statistics or {}
    original_length = max(1, statistics.get("original_length", len(text or "")))
    removed_length = max(0, statistics.get("removed_length", 0))
    low_noise = max(0.0, min(1.0, 1.0 - removed_length / original_length))
    low_repetition = _repetition_score(text or "")
    completeness = sum(bool(metadata.get(key)) for key in ("title", "author", "publish_time")) / 3
    confidence = {
        "trafilatura": 1.0,
        "plain_text": 0.95,
        "readability": 0.9,
        "bs4": 0.75,
        "fallback": 0.4,
    }.get(extraction_method, 0.5)
    if extraction_degraded:
        confidence = min(confidence, 0.4)

    score = round(
        0.20 * length_score
        + 0.20 * valid_score
        + 0.20 * low_noise
        + 0.15 * low_repetition
        + 0.15 * completeness
        + 0.10 * confidence,
        4,
    )
    if score >= 0.75:
        level, weight = "good", 1.0
    elif score >= 0.50:
        level, weight = "usable", 0.8
    elif score >= 0.30:
        level, weight = "low", 0.5
    else:
        level, weight = "very_low", 0.2

    flags: list[str] = []
    if effective_length < minimum:
        flags.append("too_short")
    if low_noise < 0.5:
        flags.append("high_noise")
    if low_repetition < 0.5:
        flags.append("high_repetition")
    if not metadata.get("publish_time"):
        flags.append("missing_publish_time")
    if not metadata.get("author"):
        flags.append("missing_author")
    if extraction_degraded:
        flags.append("extraction_degraded")

    advertisement_reasons = [
        name for name, pattern in ADVERTISEMENT_PATTERNS.items() if pattern.search(text or "")
    ]
    advertisement_score = min(1.0, len(advertisement_reasons) * 0.4)
    data = {
        "quality_score": score,
        "quality_level": level,
        "quality_flags": flags,
        "nlp_weight": weight,
        "is_advertisement": advertisement_score >= 0.4,
        "advertisement_score": advertisement_score,
        "advertisement_reasons": advertisement_reasons,
        "spam_weight": 0.5 if advertisement_score >= 0.4 else 1.0,
        "quality_version": QUALITY_VERSION,
    }
    return StageResult.success(data, QUALITY_VERSION)
