from __future__ import annotations


def analyze_sentiment(text: str) -> dict:
    return {
        "label": "中性",
        "score": 0.5,
        "reason": "情感分析接口占位，后续接入 LLM，失败降级 SnowNLP。",
        "method": "stub",
    }
