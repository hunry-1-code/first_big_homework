from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.preprocessing.result import StageResult


QUALITY_VERSION = "v1"
LENGTH_RULES = {
    "news": (80, 200),
    "social": (50, 120),    # 社交媒体至少50有效字才有分析价值
    "hotlist": (30, 80),
    "comment": (15, 50),
    "rss": (80, 200),       # RSS 新闻标准对齐 news
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
    # \u6807\u9898-\u5185\u5bb9\u4e00\u81f4\u6027\uff1a\u6807\u9898\u5b57\u8bcd\u5728\u5185\u5bb9\u4e2d\u7684\u91cd\u53e0\u5ea6
    title = str(metadata.get("title") or "")
    title_words = set(re.findall(r"[\u4e00-\u9fff]{2,}", title))
    content_words = set(re.findall(r"[\u4e00-\u9fff]{2,}", text or ""))
    title_content_overlap = len(title_words & content_words) / max(1, len(title_words)) if title_words else 1.0
    # \u9ad8\u91cd\u53e0 + \u77ed\u5185\u5bb9 = \u6807\u9898\u642c\u8fd0\uff0c\u65e0\u5b9e\u8d28\u6b63\u6587
    content_originality = 0.3 if (title_content_overlap > 0.8 and effective_length < 200) else 1.0
    confidence = {
        "trafilatura": 1.0,
        "plain_text": 0.95,
        "readability": 0.9,
        "bs4": 0.75,
        "fallback": 0.4,
    }.get(extraction_method, 0.5)
    if extraction_degraded:
        confidence = min(confidence, 0.4)

    # \u8c03\u6574\u6743\u91cd\uff1alength \u63d0\u5230 0.30\uff0cconfidence \u964d\u5230 0.05\uff0c\u52a0 content_originality
    score = round(
        0.30 * length_score
        + 0.20 * valid_score
        + 0.15 * low_noise
        + 0.10 * low_repetition
        + 0.10 * completeness
        + 0.05 * confidence
        + 0.10 * content_originality,
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
    passes_filter = bool(effective_length >= minimum and level not in ("very_low",) and not (title_content_overlap > 0.8 and effective_length < 200))
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
        "passes_filter": passes_filter,
    }
    return StageResult.success(data, QUALITY_VERSION)
