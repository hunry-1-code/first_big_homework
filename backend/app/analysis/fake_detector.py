"""虚假/可疑信息风险评估模块。

规格依据：项目需求规格说明书 §6.1 虚假/可疑信息风险评估
打分公式：§6.1.2 综合评分（初始 25 分 + 6 项加减因子，clamp 0-100，suspicious 阈值 40）
LLM 辅助：§6.1.1 Step 3（高风险事件调用 LLM，失败降级规则）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# ── 煽动性关键词列表 ────────────────────────────────────
_sensational_keywords = [
    "震惊", "炸裂", "突发", "紧急", "恐怖", "惊人", "可怕",
    "曝", "内幕", "重磅", "深度揭秘", "绝密", "独家",
    "不可思议", "难以置信", "全球震惊", "轰动", "天塌了",
    "速看", "删前速看", "紧急通知", "最新消息",
]

_ADVERTISING_PATTERNS = (
    "点击链接", "扫码领取", "扫码购买", "添加微信", "加微信",
    "私信领取", "立即购买", "限时领取", "关注公众号",
)
_URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s]+", re.IGNORECASE)
TITLE_CONTENT_CONSISTENCY_MIN = 0.30
RISK_FEATURE_WEIGHTS = {
    # 舆情平台特点：社媒作者用昵称、单平台首发都是常态，降权
    "source_traceability": 0.10,
    "cross_platform_corroboration": 0.10,
    "title_content_consistency": 0.15,
    "interaction_anomaly": 0.15,
    # 煽动/夸张/广告是虚假信息的真正信号，提权
    "sensationalism": 0.20,
    "advertising_or_external_link": 0.15,
    # 有官方媒体介入应大幅降低风险（负数 = 减分）
    "official_response": -0.15,
}


def title_content_consistency(
    title: str,
    content: str,
    semantic_similarity=None,
) -> float | None:
    if semantic_similarity is not None:
        return max(0.0, min(1.0, float(semantic_similarity(title, content))))
    title = str(title or "").strip()
    content = str(content or "").strip()[:800]
    title_length = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", title))
    content_length = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", content))
    if title_length < 4 or content_length < 8:
        return None
    title_tokens = _meaningful_tokens(title)
    body_tokens = _meaningful_tokens(content)
    if not title_tokens or not body_tokens:
        return None
    return len(title_tokens & body_tokens) / len(title_tokens)


def _meaningful_tokens(text: str) -> set[str]:
    output = set(re.findall(r"[A-Za-z0-9_]{2,}", str(text or "").casefold()))
    for segment in re.findall(r"[\u4e00-\u9fff]+", str(text or "")):
        if len(segment) == 1:
            continue
        output.update(
            segment[index : index + 2] for index in range(len(segment) - 1)
        )
    return output


def _title_content_consistency_low(title: str, content: str) -> bool:
    """Conservative wrapper for the legacy boolean risk rule."""
    score = title_content_consistency(title, content)
    return score is not None and score < TITLE_CONTENT_CONSISTENCY_MIN

# ── 官方媒体名称模式 ────────────────────────────────────
_OFFICIAL_MEDIA_PATTERNS = [
    "新闻网", "日报", "晚报", "晨报", "周报", "时报", "快报",
    "广播电台", "电视台", "发布",
    "政府网", "公安部", "法院网", "检察网",
    "人民网", "新华网", "央视网", "央广网", "中国网",
    "通讯社", "政府", "公安", "法院", "检察院",
]

_DEFAULT_OFFICIAL_MEDIA = {
    "人民日报",
    "新华社",
    "央视新闻",
    "中央广播电视总台",
    "中国新闻网",
    "中国日报",
    "光明日报",
    "经济日报",
}


def _load_official_media(path: str | None = None) -> set[str]:
    """加载官方媒体白名单。"""
    if path is None:
        path = Path(__file__).resolve().parents[3] / "data" / "official_media.txt"
    media = set(_DEFAULT_OFFICIAL_MEDIA)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if name:
                    media.add(name)
    except FileNotFoundError:
        pass
    return media


_official_media_set = _load_official_media()


def _match_official_media(author: str) -> bool:
    """判断作者是否为官方媒体（白名单精确匹配 + 名称模式匹配）。"""
    if not author or not author.strip():
        return False
    author = author.strip()
    if author in _official_media_set:
        return True
    for pattern in _OFFICIAL_MEDIA_PATTERNS:
        if pattern in author:
            return True
    return False


def _build_context(event_id: int, articles: list) -> dict:
    """从事件关联文章列表构建评估上下文。"""
    platforms = set()
    has_official = False
    total_interactions = 0
    count = 0
    corroboration_by_article = {
        getattr(article, "id", None): {
            getattr(article, "platform", "")
        }
        for article in articles
        if getattr(article, "id", None) is not None
    }
    corroboration_evidence = {
        article_id: set() for article_id in corroboration_by_article
    }

    duplicate_groups: dict[tuple[str, object], list] = {}
    for article in articles:
        article_id = getattr(article, "id", None)
        duplicate_root = getattr(article, "duplicate_of_id", None) or article_id
        if duplicate_root is not None:
            duplicate_groups.setdefault(("duplicate", duplicate_root), []).append(article)
        content_hash = getattr(article, "content_hash", None)
        if content_hash:
            duplicate_groups.setdefault(("content_hash", content_hash), []).append(article)

    for group in duplicate_groups.values():
        platforms_in_group = {
            getattr(article, "platform", "")
            for article in group
            if getattr(article, "platform", "")
        }
        if len(platforms_in_group) <= 1:
            continue
        group_ids = {
            getattr(article, "id", None)
            for article in group
            if getattr(article, "id", None) is not None
        }
        for article_id in group_ids:
            corroboration_by_article.setdefault(article_id, set()).update(
                platforms_in_group
            )
            corroboration_evidence.setdefault(article_id, set()).update(
                group_ids - {article_id}
            )

    for index, first in enumerate(articles):
        for second in articles[index + 1 :]:
            if getattr(first, "platform", None) == getattr(second, "platform", None):
                continue
            first_entities = _article_entities(first)
            second_entities = _article_entities(second)
            if not first_entities or not first_entities & second_entities:
                continue
            if _article_text_similarity(first, second) < 0.60:
                continue
            first_id = getattr(first, "id", None)
            second_id = getattr(second, "id", None)
            if first_id is None or second_id is None:
                continue
            corroboration_by_article.setdefault(first_id, set()).add(second.platform)
            corroboration_by_article.setdefault(second_id, set()).add(first.platform)
            corroboration_evidence.setdefault(first_id, set()).add(second_id)
            corroboration_evidence.setdefault(second_id, set()).add(first_id)

    for a in articles:
        platforms.add(getattr(a, "platform", ""))
        if _match_official_media(getattr(a, "author", "") or ""):
            has_official = True
        interactions = (
            (getattr(a, "comments_count", 0) or 0)
            + (getattr(a, "reposts_count", 0) or 0)
            + (getattr(a, "likes_count", 0) or 0)
        )
        total_interactions += interactions
        count += 1

    first_article = articles[0] if articles else None
    return {
        "event_id": event_id,
        "article_count": count,
        "platforms": platforms,
        "has_official_media": has_official,
        "first_publish_time": getattr(first_article, "publish_time", None) if first_article else None,
        "avg_interactions": total_interactions / count if count > 0 else 0,
        "corroboration_by_article": corroboration_by_article,
        "corroboration_evidence_by_article": {
            article_id: sorted(evidence_ids)
            for article_id, evidence_ids in corroboration_evidence.items()
        },
    }


def _article_entities(article) -> set[str]:
    output = set()
    entities = getattr(article, "entities", None) or {}
    if isinstance(entities, dict):
        for values in entities.values():
            if isinstance(values, str):
                values = [values]
            output.update(str(value).strip().casefold() for value in values or [] if str(value).strip())
    keywords = getattr(article, "keywords", None) or []
    if isinstance(keywords, dict):
        keywords = keywords.get("keywords", [])
    for item in keywords if isinstance(keywords, (list, tuple, set)) else []:
        value = item.get("term") if isinstance(item, dict) else item
        if str(value or "").strip():
            output.add(str(value).strip().casefold())
    return output


def _article_text_similarity(first, second) -> float:
    def bigrams(article):
        text = (
            (getattr(article, "title", "") or "")
            + (getattr(article, "clean_content", "") or "")[:300]
        )
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
        return {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}

    left = bigrams(first)
    right = bigrams(second)
    return len(left & right) / len(left | right) if left and right else 0.0


def _estimate_anomaly_speed(article, ctx: dict) -> bool:
    """估计传播速度是否异常。

    判断：发布时间距离事件首发 < 1 小时，且互动量 > 同事件平均的 2 倍。
    """
    pub_time = getattr(article, "publish_time", None)
    first_time = ctx.get("first_publish_time")
    if pub_time is None or first_time is None:
        return False

    from datetime import timedelta

    try:
        delta = pub_time - first_time
    except TypeError:
        return False
    if isinstance(delta, timedelta) and delta.total_seconds() > 3600:
        return False

    interactions = (
        (getattr(article, "comments_count", 0) or 0)
        + (getattr(article, "reposts_count", 0) or 0)
        + (getattr(article, "likes_count", 0) or 0)
    )
    avg = ctx.get("avg_interactions", 0)
    return avg > 0 and interactions > avg * 2


def _interaction_anomaly_score(article, ctx: dict) -> float:
    interactions = (
        (getattr(article, "comments_count", 0) or 0)
        + (getattr(article, "reposts_count", 0) or 0)
        + (getattr(article, "likes_count", 0) or 0)
    )
    average = float(ctx.get("avg_interactions", 0) or 0)
    if average <= 0:
        return 0.0
    ratio = interactions / average
    return max(0.0, min(1.0, (ratio - 1.0) / 2.0))


def assess_suspicious_risk(article, ctx: dict) -> dict:
    """对单篇文章进行可疑信息风险评估。

    规格依据：项目需求规格说明书 §6.1.2 综合评分
    """
    reasons = []
    feature_scores = {}
    evidence = {}

    # 1. 来源可信度：作者未知或无标识 +15
    author = (getattr(article, "author", None) or "").strip()
    is_official = _match_official_media(author)
    if not author or author in ("未知", "匿名", "佚名"):
        reasons.append("来源可信度较低（作者不可溯源）")
        feature_scores["source_traceability"] = 1.0
    else:
        feature_scores["source_traceability"] = 0.0

    # 2. 文章级交叉验证：该文章没有跨平台重复或高相似佐证 +15
    article_id = getattr(article, "id", None)
    corroboration = ctx.get("corroboration_by_article", {}).get(article_id)
    if corroboration is None:
        corroboration = {getattr(article, "platform", "")}
    corroboration = {value for value in corroboration if value}
    evidence_ids = list(
        ctx.get("corroboration_evidence_by_article", {}).get(article_id, [])
    )
    missing_corroboration = len(corroboration) <= 1
    if missing_corroboration:
        reasons.append("缺少跨平台佐证")
    feature_scores["cross_platform_corroboration"] = (
        1.0 if missing_corroboration else 0.0
    )
    evidence["cross_platform_corroboration"] = {
        "platforms": sorted(corroboration),
        "article_ids": evidence_ids,
    }

    # 3. 标题煽动性：命中关键词 +10
    title = (getattr(article, "title", "") or "").strip()
    content = (getattr(article, "clean_content", "") or "").strip()
    text = title + content[:200]
    hit_keywords = [kw for kw in _sensational_keywords if kw in text]
    if hit_keywords:
        reasons.append(f"标题/正文存在夸张煽动表达: {', '.join(hit_keywords[:3])}")
    feature_scores["sensationalism"] = min(1.0, len(set(hit_keywords)) / 3.0)
    evidence["sensationalism"] = hit_keywords[:3]

    # Supplemental low-weight textual signals. None is sufficient to label a text fake.
    hit_ads = [pattern for pattern in _ADVERTISING_PATTERNS if pattern in content]
    if hit_ads:
        reasons.append(f"正文存在广告引流表达: {', '.join(hit_ads[:2])}")

    has_external_link = bool(_URL_PATTERN.search(content))
    if has_external_link:
        reasons.append("正文包含外部链接，需核验链接来源")
    feature_scores["advertising_or_external_link"] = (
        1.0 if hit_ads else 0.4 if has_external_link else 0.0
    )

    consistency_score = title_content_consistency(title, content)
    low_consistency = (
        consistency_score is not None
        and consistency_score < TITLE_CONTENT_CONSISTENCY_MIN
    )
    if low_consistency:
        reasons.append("标题与正文一致性较低")
    feature_scores["title_content_consistency"] = (
        round(1.0 - consistency_score, 6)
        if consistency_score is not None
        else 0.0
    )
    evidence["title_content_consistency"] = {
        "score": round(consistency_score, 6) if consistency_score is not None else None,
        "status": "insufficient" if consistency_score is None else "available",
    }

    # 4. 负面情绪：score < -0.5 +10
    sentiment = getattr(article, "sentiment_score", None)
    if sentiment is not None and sentiment < -0.5:
        evidence["negative_sentiment"] = {
            "score": float(sentiment),
            "note": "情绪极性不直接计入可疑信息风险分",
        }
    feature_scores["negative_sentiment"] = (
        1.0 if sentiment is not None and sentiment < -0.5 else 0.0
    )

    # 5. 传播速度异常 +10
    anomaly_score = _interaction_anomaly_score(article, ctx)
    anomalous_speed = anomaly_score > 0.5
    if anomalous_speed:
        reasons.append("传播速度异常")
    feature_scores["interaction_anomaly"] = round(anomaly_score, 6)

    # 6. 官方回应：有官方媒体介入 -20
    if ctx.get("has_official_media", False):
        reasons.append("有官方媒体或权威来源回应")
    feature_scores["official_response"] = (
        1.0 if ctx.get("has_official_media", False) else 0.0
    )

    score = sum(
        RISK_FEATURE_WEIGHTS[name] * feature_scores[name]
        for name in RISK_FEATURE_WEIGHTS
    ) * 100
    score = max(0.0, min(100.0, score))
    is_suspicious = score >= 40

    return {
        "is_suspicious": is_suspicious,
        "score": round(score, 1),
        "reason": "; ".join(reasons) if reasons else "未发现明显风险因素",
        "method": "rule",
        "feature_scores": feature_scores,
        "evidence": evidence,
        "limitations": (
            ["缺少文章级跨平台佐证数据"]
            if article_id not in ctx.get("corroboration_by_article", {})
            else []
        ),
        "rule_version": "suspicious-risk-v3-empirical",
    }


def _parse_llm_review(response: dict) -> dict | None:
    content = str((response or {}).get("content", "") or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict) or not str(value.get("reason", "")).strip():
        return None
    return {
        "risk_level": str(value.get("risk_level", "uncertain"))[:24],
        "reason": str(value.get("reason", "")).strip()[:500],
        "confidence": max(0.0, min(1.0, float(value.get("confidence", 0) or 0))),
        "model": (response or {}).get("model"),
    }


def batch_assess_articles(
    articles: list,
    ctx: dict,
    *,
    client=None,
    llm_min_score: float | None = None,
    llm_max_score: float | None = None,
) -> list[dict]:
    """批量评估文章可疑风险。

    对评分 > 70 的文章尝试调用 LLM 做辅助分析，
    LLM 调用失败时降级为纯规则评分（method="rule"），
    LLM 成功时 method="mixed"。
    规格依据：§9.3 LLM 调用失败降级策略
    """
    if not articles:
        return []

    results = []
    from app.core.config import Config

    minimum = float(
        Config.RISK_LLM_MIN_SCORE if llm_min_score is None else llm_min_score
    )
    maximum = float(
        Config.RISK_LLM_MAX_SCORE if llm_max_score is None else llm_max_score
    )
    _llm_client = client

    for article in articles:
        result = assess_suspicious_risk(article, ctx)
        if minimum <= result["score"] <= maximum:
            try:
                from app.llm.client import LLMUnavailableError

                try:
                    if _llm_client is None:
                        from app.llm.client import LLMClient

                        _llm_client = LLMClient(
                            api_key=Config.LLM_API_KEY,
                            base_url=Config.LLM_BASE_URL,
                            model_name=Config.LLM_MODEL_NAME,
                            timeout=30,
                        )

                    llm_title = getattr(article, "title", "")
                    llm_content = (getattr(article, "clean_content", "") or "")[:200]
                    resp = _llm_client.chat([{
                        "role": "user",
                        "content": (
                            "判断以下信息是否存在可疑风险。只返回 JSON："
                            '{"risk_level":"low|medium|high","reason":"...","confidence":0.0}\n'
                            f"标题：{llm_title}\n内容：{llm_content}\n"
                            f"当前规则评分：{result['score']}/100\n"
                            f"已有风险因素：{result['reason']}"
                        ),
                    }])
                    review = _parse_llm_review(resp)
                    if review:
                        result["evidence"]["llm_review"] = review
                        result["reason"] = (
                            f"[规则] {result['reason']} | [LLM] {review['reason']}"
                        )
                        result["method"] = "mixed"
                except LLMUnavailableError:
                    pass  # LLM 不可用，保持 rule
            except Exception:
                pass  # 任何异常都不影响 rule 结果

        results.append(result)

    return results
