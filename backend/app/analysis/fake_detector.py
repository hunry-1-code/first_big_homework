"""虚假/可疑信息风险评估模块。

规格依据：项目需求规格说明书 §6.1 虚假/可疑信息风险评估
打分公式：§6.1.2 综合评分（初始 25 分 + 6 项加减因子，clamp 0-100，suspicious 阈值 40）
LLM 辅助：§6.1.1 Step 3（高风险事件调用 LLM，失败降级规则）
"""
from __future__ import annotations

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


def _title_content_consistency_low(title: str, content: str) -> bool:
    """Conservative character-overlap check for obviously unrelated Chinese text."""
    title_chars = {char for char in title if "\u4e00" <= char <= "\u9fff"}
    content_chars = {char for char in content[:500] if "\u4e00" <= char <= "\u9fff"}
    if len(title_chars) < 6 or len(content_chars) < 10:
        return False
    return len(title_chars & content_chars) / len(title_chars) < 0.15

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
    }


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


def assess_suspicious_risk(article, ctx: dict) -> dict:
    """对单篇文章进行可疑信息风险评估。

    规格依据：项目需求规格说明书 §6.1.2 综合评分
    """
    score = 25.0
    reasons = []

    # 1. 来源可信度：作者未知或无标识 +15
    author = (getattr(article, "author", None) or "").strip()
    is_official = _match_official_media(author)
    if not author or author in ("未知", "匿名", "佚名"):
        score += 15
        reasons.append("来源可信度较低（作者不可溯源）")

    # 2. 多源交叉验证：只有一个平台报道 +15
    platforms = ctx.get("platforms", set())
    if len(platforms) <= 1:
        score += 15
        reasons.append("缺少多源交叉验证")

    # 3. 标题煽动性：命中关键词 +10
    title = (getattr(article, "title", "") or "").strip()
    content = (getattr(article, "clean_content", "") or "").strip()
    text = title + content[:200]
    hit_keywords = [kw for kw in _sensational_keywords if kw in text]
    if hit_keywords:
        score += 10
        reasons.append(f"标题/正文存在夸张煽动表达: {', '.join(hit_keywords[:3])}")

    # Supplemental low-weight textual signals. None is sufficient to label a text fake.
    hit_ads = [pattern for pattern in _ADVERTISING_PATTERNS if pattern in content]
    if hit_ads:
        score += 8
        reasons.append(f"正文存在广告引流表达: {', '.join(hit_ads[:2])}")

    if _URL_PATTERN.search(content):
        score += 3
        reasons.append("正文包含外部链接，需核验链接来源")

    if _title_content_consistency_low(title, content):
        score += 5
        reasons.append("标题与正文一致性较低")

    # 4. 负面情绪：score < -0.5 +10
    sentiment = getattr(article, "sentiment_score", None)
    if sentiment is not None and sentiment < -0.5:
        score += 10
        reasons.append("负面情绪比例较高")

    # 5. 传播速度异常 +10
    if _estimate_anomaly_speed(article, ctx):
        score += 10
        reasons.append("传播速度异常")

    # 6. 官方回应：有官方媒体介入 -20
    if ctx.get("has_official_media", False):
        score -= 20
        reasons.append("有官方媒体或权威来源回应")

    score = max(0.0, min(100.0, score))
    is_suspicious = score >= 40

    return {
        "is_suspicious": is_suspicious,
        "score": round(score, 1),
        "reason": "; ".join(reasons) if reasons else "未发现明显风险因素",
        "method": "rule",
    }


def batch_assess_articles(articles: list, ctx: dict) -> list[dict]:
    """批量评估文章可疑风险。

    对评分 > 70 的文章尝试调用 LLM 做辅助分析，
    LLM 调用失败时降级为纯规则评分（method="rule"），
    LLM 成功时 method="mixed"。
    规格依据：§9.3 LLM 调用失败降级策略
    """
    if not articles:
        return []

    results = []
    _llm_client = None

    for article in articles:
        result = assess_suspicious_risk(article, ctx)
        # 高风险文章尝试 LLM 辅助
        if result["score"] >= 70:
            try:
                from app.llm.client import LLMUnavailableError

                try:
                    from app.core.config import settings

                    if _llm_client is None:
                        from app.llm.client import LLMClient

                        _llm_client = LLMClient(
                            api_key=getattr(settings, "LLM_API_KEY", ""),
                            base_url=getattr(settings, "LLM_BASE_URL", ""),
                            model_name=getattr(settings, "LLM_MODEL_NAME", ""),
                            timeout=30,
                        )

                    llm_title = getattr(article, "title", "")
                    llm_content = (getattr(article, "clean_content", "") or "")[:200]
                    resp = _llm_client.chat([{
                        "role": "user",
                        "content": (
                            f"判断以下信息是否存在虚假或可疑风险，用一句话说明原因：\n"
                            f"标题：{llm_title}\n内容：{llm_content}\n"
                            f"当前规则评分：{result['score']}/100\n"
                            f"已有风险因素：{result['reason']}"
                        ),
                    }])
                    llm_reason = resp.get("content", "").strip()
                    if llm_reason:
                        result["reason"] = f"[规则] {result['reason']} | [LLM] {llm_reason}"
                        result["method"] = "mixed"
                except LLMUnavailableError:
                    pass  # LLM 不可用，保持 rule
            except Exception:
                pass  # 任何异常都不影响 rule 结果

        results.append(result)

    return results
