"""LLM 关键词提取 — 替代 TF-IDF 分词"""
from __future__ import annotations
import json, re
from typing import Iterable


def _llm_client():
    from flask import current_app
    from app.llm.client import LLMClient
    return LLMClient(
        api_key=current_app.config.get("LLM_API_KEY", ""),
        base_url=current_app.config.get("LLM_BASE_URL", ""),
        model_name=current_app.config.get("LLM_MODEL_NAME", ""),
        timeout=15,
    )


def extract_keywords_llm(documents: Iterable, max_per_doc: int = 8) -> dict[int, list[dict]]:
    """用 LLM 从文章中提取关键词，批量处理减少调用次数。

    每篇文章返回 5-8 个关键词及重要性分数（0-1），分词准确且无语义噪声。
    失败时回退到空列表，不影响流程。
    """
    from app.analysis.feature_config import FeatureConfig
    from app.analysis.keyword_extractor import extract_article_keywords as _tfidf_extract
    from app.analysis.result import AnalysisDocument, FeatureMatrixResult

    output: dict[int, list[dict]] = {}
    client = None

    for doc in documents:
        if not isinstance(doc, AnalysisDocument):
            continue
        text = doc.analysis_text if hasattr(doc, 'analysis_text') else (
            (doc.title or '') + ' ' + ' '.join(doc.body_tokens or [])
        )
        if len(text.strip()) < 20:
            continue

        try:
            if client is None:
                client = _llm_client()
            resp = client.chat([
                {"role": "system", "content": (
                    "你是中文关键词提取器。从给定文本中提取 5-8 个最有代表性的关键词，"
                    "每个词 2-6 个字，排除停用词和通用词。返回 JSON 数组："
                    '[{"term":"关键词","score":0.95},...]'
                    "score 0-1 表示重要性，不要加解释文字。"
                )},
                {"role": "user", "content": f"提取关键词：{text[:800]}"}
            ], temperature=0.1, max_tokens=200)

            content = resp["content"].strip()
            fenced = re.fullmatch(
                r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE
            )
            if fenced:
                content = fenced.group(1)
            parsed = json.loads(content)

            if isinstance(parsed, list):
                items = []
                for item in parsed[:max_per_doc]:
                    if isinstance(item, dict) and item.get("term"):
                        items.append({
                            "term": str(item["term"]).strip()[:20],
                            "score": round(float(item.get("score", 0.5)), 4),
                            "rank": len(items) + 1,
                            "source": "llm",
                            "type": "word",
                        })
                if items:
                    output[doc.article_id] = items
        except Exception:
            pass  # LLM 不可用时静默跳过

    return output


def _merge_llm_keywords(
    llm_result: dict[int, list[dict]],
    tfidf_result: dict[int, list],
) -> dict[int, list]:
    """LLM 关键词优先，缺失的文章回退 TF-IDF。"""
    merged = {}
    for article_id in set(list(llm_result.keys()) + list(tfidf_result.keys())):
        llm_kw = llm_result.get(article_id)
        if llm_kw and len(llm_kw) >= 3:
            merged[article_id] = llm_kw
        else:
            merged[article_id] = tfidf_result.get(article_id, [])
    return merged
