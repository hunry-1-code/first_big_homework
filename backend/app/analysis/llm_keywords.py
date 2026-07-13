"""批量 LLM 多维关键词提取，缺失文章由确定性关键词结果回退。"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable


_SYSTEM_PROMPT = """你是舆情关键词提取器。输入是文章 JSON 数组，每项包含 article_id 和 text。
返回一个 JSON 对象，键必须是 article_id 字符串，值为该文章的 5-8 个关键词数组。
每个关键词字段：term、score(0-1)、sentiment(positive/negative/neutral)、entity_type(location/organization/person/event/concept)。
只返回 JSON，不添加解释；不得返回输入中不存在的 article_id。"""

_VALID_SENTIMENTS = {"positive", "negative", "neutral"}
_VALID_TYPES = {"location", "organization", "person", "event", "concept"}


def _llm_client():
    from flask import current_app
    from app.llm.client import LLMClient

    return LLMClient(
        api_key=current_app.config.get("LLM_API_KEY", ""),
        base_url=current_app.config.get("LLM_BASE_URL", ""),
        model_name=current_app.config.get("LLM_MODEL_NAME", ""),
        timeout=15,
    )


def _json_value(content: str):
    text = str(content or "").strip()
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE
    )
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def _normalize_items(values, max_per_doc: int) -> list[dict]:
    if not isinstance(values, list):
        return []
    output = []
    for item in values:
        if len(output) >= max(1, int(max_per_doc)):
            break
        if not isinstance(item, dict):
            continue
        term = str(item.get("term", "") or "").strip()[:20]
        if not term:
            continue
        try:
            score = float(item.get("score", 0.5))
        except (TypeError, ValueError):
            continue
        sentiment = str(item.get("sentiment", "neutral")).strip().lower()
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"
        entity_type = str(
            item.get("entity_type", item.get("type", "concept"))
        ).strip().lower()
        if entity_type not in _VALID_TYPES:
            entity_type = "concept"
        output.append(
            {
                "term": term,
                "score": round(max(0.0, min(1.0, score)), 4),
                "rank": len(output) + 1,
                "source": "llm",
                "type": entity_type,
                "sentiment": sentiment,
            }
        )
    return output


def _parse_response(content: str, max_per_doc: int = 8) -> list[dict]:
    """兼容旧的单文章 JSON 数组响应。"""
    try:
        return _normalize_items(_json_value(content), max_per_doc)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _parse_batch_response(
    content: str,
    *,
    allowed_ids: set[int],
    max_per_doc: int = 8,
) -> dict[int, list[dict]]:
    try:
        parsed = _json_value(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    output = {}
    for raw_id, values in parsed.items():
        try:
            article_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if article_id not in allowed_ids:
            continue
        items = _normalize_items(values, max_per_doc)
        if items:
            output[article_id] = items
    return output


def extract_keywords_llm(
    documents: Iterable,
    max_per_doc: int = 8,
    *,
    client=None,
    batch_size: int = 5,
) -> dict[int, list[dict]]:
    """按批请求 LLM；批次失败或漏项时不伪造结果，由调用方回退。"""
    from app.analysis.result import AnalysisDocument

    valid_documents = []
    for document in documents:
        if not isinstance(document, AnalysisDocument):
            continue
        text = f"{document.title or ''} {' '.join(document.body_tokens or [])}".strip()
        if len(text) < 20:
            continue
        valid_documents.append((document.article_id, text[:800]))

    output: dict[int, list[dict]] = {}
    effective_client = client
    size = max(1, int(batch_size))
    for start in range(0, len(valid_documents), size):
        batch = valid_documents[start : start + size]
        payload = [
            {"article_id": article_id, "text": text}
            for article_id, text in batch
        ]
        try:
            if effective_client is None:
                effective_client = _llm_client()
            response = effective_client.chat(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
                temperature=0.1,
                max_tokens=max(300, len(batch) * 220),
            )
            output.update(
                _parse_batch_response(
                    response.get("content", ""),
                    allowed_ids={article_id for article_id, _text in batch},
                    max_per_doc=max_per_doc,
                )
            )
        except Exception:
            continue
    return output


def _merge_llm_keywords(
    llm_result: dict[int, list[dict]],
    tfidf_result: dict[int, list],
) -> dict[int, list]:
    """LLM 至少三个有效词时优先，否则逐篇回退 TF-IDF。"""
    merged = {}
    for article_id in set(llm_result) | set(tfidf_result):
        llm_keywords = _normalize_items(llm_result.get(article_id), 8)
        if len(llm_keywords) >= 3:
            merged[article_id] = llm_keywords
            continue
        fallback = []
        for item in tfidf_result.get(article_id, []):
            if hasattr(item, "as_dict"):
                value = item.as_dict()
            elif isinstance(item, dict):
                value = dict(item)
            else:
                continue
            value.setdefault("sentiment", "neutral")
            value.setdefault("type", value.get("entity_type", "concept"))
            fallback.append(value)
        merged[article_id] = fallback
    return merged


__all__ = [
    "_merge_llm_keywords",
    "_parse_batch_response",
    "_parse_response",
    "extract_keywords_llm",
]
