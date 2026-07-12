from __future__ import annotations

import re
import unicodedata

from app.preprocessing.result import StageResult


SEGMENT_VERSION = "v1"
DEFAULT_STOPWORDS = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "及",
    "一个",
    "我们",
    "他们",
    "这个",
    "那个",
}
SENTIMENT_TERMS = {"不", "没", "没有", "非常", "很", "太", "过于", "极其", "更加"}


def _fallback_tokens(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]|[A-Za-z]+|\d+(?:\.\d+)?", text)


def segment_document(
    text: str,
    topics: list[str] | None = None,
    mentions: list[str] | None = None,
    stopwords: set[str] | None = None,
) -> StageResult:
    analysis_text = unicodedata.normalize("NFKC", text or "")
    warnings: list[str] = []
    try:
        import jieba

        tokens = [token.strip() for token in jieba.cut(analysis_text, cut_all=False)]
    except (ImportError, RuntimeError):
        tokens = _fallback_tokens(analysis_text)
        warnings.append("SEGMENT_JIEBA_ERROR")

    normalized: list[str] = []
    for token in tokens:
        token = token.lower().strip()
        if not token or re.fullmatch(r"[\s\W_]+", token):
            continue
        normalized.append(token)
    normalized.extend(item for item in (topics or []) if item not in normalized)
    normalized.extend(item for item in (mentions or []) if item not in normalized)

    excluded = DEFAULT_STOPWORDS | (stopwords or set())
    tfidf_tokens = [token for token in normalized if token not in excluded]
    sentiment_tokens = [
        token for token in normalized if token not in excluded or token in SENTIMENT_TERMS
    ]
    data = {
        "tokens": normalized,
        "tfidf_tokens": tfidf_tokens,
        "sentiment_tokens": sentiment_tokens,
        "topics": list(topics or []),
        "mentions": list(mentions or []),
        "segment_version": SEGMENT_VERSION,
    }
    if warnings:
        return StageResult.degraded(data, warnings, SEGMENT_VERSION)
    return StageResult.success(data, SEGMENT_VERSION)


def segment_text(text: str) -> list[str]:
    return segment_document(text).data["tokens"]
