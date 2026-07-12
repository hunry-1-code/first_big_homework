"""LLM 多维度关键词提取 — 通用舆情分析，解耦领域

提取维度：term(词) / score(重要性) / sentiment(情感倾向) / entity_type(实体类型)
适用任意舆情领域（自然灾害、政治、经济、公共卫生、社会事件等）。
"""
from __future__ import annotations
import json, re
from typing import Iterable

# ── 通用提示词，不绑定任何特定领域 ──
_SYSTEM_PROMPT = """你是舆情关键词提取器。从文本中提取 5-8 个关键信息点，返回 JSON 数组。

每个元素的字段：
- term: 关键词（2-8 字，中文）
- score: 重要性 0-1（越高越核心）
- sentiment: 情感倾向（positive=肯定/利好, negative=负面/批评/风险, neutral=客观陈述）
- entity_type: 实体类型（location=地名, organization=机构/组织, person=人物, event=事件名, concept=抽象概念/话题）

规则：
1. 只提取对理解事件有实质帮助的词，排除"的""了""是""在"等虚词
2. sentiment 根据该词在文中的上下文判断，不是根据词本身
3. 地名至少出现 1 个（如有），机构/人物名尽量提取
4. 不添加解释文字，纯 JSON 数组输出"""

_USER_PROMPT = "从以下文本提取关键词：{text}"


def _llm_client():
    from flask import current_app
    from app.llm.client import LLMClient
    return LLMClient(
        api_key=current_app.config.get("LLM_API_KEY", ""),
        base_url=current_app.config.get("LLM_BASE_URL", ""),
        model_name=current_app.config.get("LLM_MODEL_NAME", ""),
        timeout=15,
    )


def _parse_response(content: str, max_per_doc: int = 8) -> list[dict]:
    """解析 LLM 返回的 JSON，容错处理。"""
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        return []

    valid_sentiments = {"positive", "negative", "neutral"}
    valid_types = {"location", "organization", "person", "event", "concept"}
    items = []
    for item in parsed[:max_per_doc]:
        if not isinstance(item, dict) or not item.get("term"):
            continue
        term = str(item["term"]).strip()[:20]
        sentiment = str(item.get("sentiment", "neutral")).strip().lower()
        if sentiment not in valid_sentiments:
            sentiment = "neutral"
        entity = str(item.get("entity_type", "concept")).strip().lower()
        if entity not in valid_types:
            entity = "concept"
        items.append({
            "term": term,
            "score": round(float(item.get("score", 0.5)), 4),
            "rank": len(items) + 1,
            "source": "llm",
            "type": entity,
            "sentiment": sentiment,
        })
    return items


def extract_keywords_llm(documents: Iterable, max_per_doc: int = 8) -> dict[int, list[dict]]:
    """LLM 多维度关键词提取。失败静默跳过，不影响流程。"""
    output: dict[int, list[dict]] = {}
    client = None

    for doc in documents:
        from app.analysis.result import AnalysisDocument
        if not isinstance(doc, AnalysisDocument):
            continue
        text = (doc.title or "") + " " + " ".join(doc.body_tokens or [])
        if len(text.strip()) < 20:
            continue

        try:
            if client is None:
                client = _llm_client()
            resp = client.chat([
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_PROMPT.format(text=text[:800])}
            ], temperature=0.1, max_tokens=300)
            items = _parse_response(resp["content"], max_per_doc)
            if items:
                output[doc.article_id] = items
        except Exception:
            pass

    return output


def _merge_llm_keywords(
    llm_result: dict[int, list[dict]],
    tfidf_result: dict[int, list],
) -> dict[int, list]:
    """LLM 优先，缺失文章回退 TF-IDF。TF-IDF 词标记为 sentiment=neutral, type=concept。"""
    merged = {}
    for article_id in set(list(llm_result.keys()) + list(tfidf_result.keys())):
        llm_kw = llm_result.get(article_id)
        if llm_kw and len(llm_kw) >= 3:
            merged[article_id] = llm_kw
        else:
            # TF-IDF 回退词补充默认字段
            fallback = []
            for item in tfidf_result.get(article_id, []):
                if hasattr(item, 'as_dict'):
                    d = item.as_dict()
                elif isinstance(item, dict):
                    d = dict(item)
                else:
                    continue
                d.setdefault("sentiment", "neutral")
                d.setdefault("type", d.get("entity_type", "concept"))
                fallback.append(d)
            merged[article_id] = fallback
    return merged
