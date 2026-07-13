from __future__ import annotations

import json
import re
from typing import Callable

from app.analysis.sentiment_config import SentimentConfig
from app.llm.prompts import SENTIMENT_PROMPT


LABELS = {"positive", "negative", "neutral"}
DIMENSIONS = {"stance", "impact", "factual"}


class SentimentAnalysisError(ValueError):
    pass


def _strip_json_fence(value: str) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def _normalized_result(payload: dict, *, method: str, model_name: str | None) -> dict:
    label = str(payload.get("label") or "").strip().casefold()
    dimension = str(payload.get("dimension") or "").strip().casefold()
    if label not in LABELS:
        raise SentimentAnalysisError("情感标签不合法")
    if dimension not in DIMENSIONS:
        raise SentimentAnalysisError("情感判定维度不合法")
    try:
        score = float(payload.get("score"))
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise SentimentAnalysisError("情感分数或置信度不合法") from exc
    if not -1 <= score <= 1 or not 0 <= confidence <= 1:
        raise SentimentAnalysisError("情感分数或置信度越界")
    if label == "positive" and score < 0:
        raise SentimentAnalysisError("正面标签与负向分数冲突")
    if label == "negative" and score > 0:
        raise SentimentAnalysisError("负面标签与正向分数冲突")
    target = " ".join(str(payload.get("target") or "").split())[:200]
    reason = " ".join(str(payload.get("reason") or "").split())[:500]
    if not target or not reason:
        raise SentimentAnalysisError("情感目标和理由不能为空")
    return {
        "label": label,
        "score": round(score, 6),
        "confidence": round(confidence, 6),
        "dimension": dimension,
        "target": target,
        "reason": reason,
        "method": method,
        "model_name": model_name,
        "warnings": [],
    }


def analyze_sentiment(
    text: str,
    *,
    context: dict | None = None,
    client=None,
    config: SentimentConfig | None = None,
) -> dict:
    config = config or SentimentConfig()
    if client is None:
        raise SentimentAnalysisError("LLM 客户端不可用")
    cleaned = " ".join(str(text or "").split())[: config.text_limit]
    if not cleaned:
        raise SentimentAnalysisError("情感分析文本为空")
    context = dict(context or {})
    user_content = json.dumps(
        {
            "topic_category": context.get("topic_category"),
            "topic_name": context.get("topic_name"),
            "event_title": context.get("event_title"),
            "article_title": context.get("article_title"),
            "text": cleaned,
        },
        ensure_ascii=False,
    )
    response = client.chat(
        [
            {"role": "system", "content": SENTIMENT_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    try:
        payload = json.loads(_strip_json_fence(response.get("content", "")))
    except (TypeError, json.JSONDecodeError) as exc:
        raise SentimentAnalysisError("LLM 情感输出不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise SentimentAnalysisError("LLM 情感输出必须是 JSON 对象")
    result = _normalized_result(
        payload,
        method="llm",
        model_name=response.get("model") or getattr(client, "model_name", None),
    )
    result["raw_response"] = payload
    return result


def analyze_with_snownlp(
    text: str,
    *,
    probability_fn: Callable[[str], float] | None = None,
    config: SentimentConfig | None = None,
    context: dict | None = None,
) -> dict:
    config = config or SentimentConfig()
    cleaned = " ".join(str(text or "").split())[: config.text_limit]
    if not cleaned:
        raise SentimentAnalysisError("情感分析文本为空")
    if probability_fn is None:
        try:
            from snownlp import SnowNLP
        except ImportError as exc:
            raise SentimentAnalysisError("SnowNLP 不可用") from exc
        probability_fn = lambda value: float(SnowNLP(value).sentiments)
    probability = max(0.0, min(1.0, float(probability_fn(cleaned))))
    score = round(2 * probability - 1, 6)
    if probability >= config.snownlp_positive_threshold:
        label = "positive"
    elif probability <= config.snownlp_negative_threshold:
        label = "negative"
    else:
        label = "neutral"
    category = str((context or {}).get("topic_category") or "")
    dimension = "impact" if category in {"自然灾害", "社会事件"} else "factual"
    confidence = min(config.snownlp_confidence_cap, abs(score))
    return {
        "label": label,
        "score": score,
        "confidence": round(confidence, 6),
        "dimension": dimension,
        "target": str((context or {}).get("event_title") or "文本整体倾向")[:200],
        "reason": "LLM 不可用，使用 SnowNLP 概率模型降级判断。",
        "method": "snownlp",
        "model_name": "snownlp",
        "warnings": ["SNOWNLP_FALLBACK", "DOMAIN_MISMATCH_FALLBACK"],
    }


__all__ = [
    "SentimentAnalysisError",
    "analyze_sentiment",
    "analyze_with_snownlp",
]
