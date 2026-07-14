from collections import Counter
import re
from app.models import Article, Comment

# SnowNLP 对短文本不可靠，用关键词规则覆盖
# 短评论情感关键词（<30字时 SnowNLP 不可靠，规则覆盖）
NEGATIVE_STRONG = ("举报", "可怕", "恐怖", "灾难", "惨", "死", "救命", "害人", "造孽")
NEGATIVE_WEAK = ("不满", "没人管", "失望", "愤怒", "质疑", "投诉", "糟糕", "骗人", "苦难", "娱乐化",
                  "活该", "无语", "恶心", "过分", "荒唐", "悲哀", "心疼", "担心", "害怕",
                  "吓人", "完了", "不好", "受罪", "遭殃", "可怜", "倒霉")
POSITIVE_STRONG = ("支持", "感谢", "点赞", "辛苦", "加油", "平安", "保佑", "致敬", "好人")
POSITIVE_WEAK = ("很好", "不错", "厉害", "棒", "优秀", "赞", "好样的", "给力", "牛",
                  "暖心", "感动", "希望能", "顺利", "安全", "注意安全", "注意防范", "挺住")

def _comment_weight(item) -> float:
    """评论质量权重：长度为主 + 点赞为辅，上限 1.0"""
    length = len(item.content or "")
    likes = item.likes_count or 0
    w_len = min(1.0, length / 50.0)        # 50字以上满分
    w_likes = min(1.0, likes / 10.0)        # 10赞以上满分
    return round(w_len * 0.6 + w_likes * 0.4, 4)  # 长度权重高于点赞（56%评论0赞）

def _correct_sentiment(text: str, original_label: str | None) -> str:
    """短评论（<30字）SnowNLP 不可靠，用关键词规则覆盖。"""
    if not text or len(text) >= 30:
        return original_label or "neutral"
    has_neg_strong = any(w in text for w in NEGATIVE_STRONG)
    has_neg_weak = any(w in text for w in NEGATIVE_WEAK)
    has_pos_strong = any(w in text for w in POSITIVE_STRONG)
    has_pos_weak = any(w in text for w in POSITIVE_WEAK)
    if has_neg_strong:
        return "negative"
    if has_neg_weak and not has_pos_strong:
        return "negative"
    if has_pos_strong and not has_neg_strong:
        return "positive"
    if has_pos_weak and not has_neg_weak:
        return "positive"
    return original_label or "neutral"

def get_public_opinion_snapshot(event_id: int) -> dict:
    article_ids = [row[0] for row in Article.query.with_entities(Article.id).filter_by(event_id=event_id).all()]
    comments = Comment.query.filter(Comment.article_id.in_(article_ids)).all() if article_ids else []
    # 加权情感统计（频次增强 + 用户去重）
    counts = Counter()
    counts_raw = Counter()
    corrected_count = 0
    content_freq: dict[str, int] = Counter()  # 相同内容出现次数
    user_content: dict[str, set] = {}  # 每个用户对每条内容的去重

    # 第一遍：统计频次
    for item in comments:
        text = (item.content or "").strip().casefold()
        if text and len(text) >= 2:
            content_freq[text] += 1

    for item in comments:
        text = item.content or ""
        label = item.sentiment_label
        corrected = _correct_sentiment(text, label)
        if corrected != label:
            corrected_count += 1
        weight = _comment_weight(item)

        # 用户去重：同一用户发相同内容只计一次
        dedup_key = text.strip().casefold()
        author = (item.author or "").strip()
        if dedup_key and author:
            user_key = f"{author}:{dedup_key}"
            if user_key in user_content.get(dedup_key, set()):
                continue
            user_content.setdefault(dedup_key, set()).add(user_key)

        # 频次增强：多人同感是重要信号，最多放大 2.5 倍
        freq = content_freq.get(dedup_key, 1) if dedup_key else 1
        freq_boost = min(2.5, 1.0 + (freq - 1) * 0.15)  # 1次=1x, 11次=2.5x
        counts[corrected] += weight * freq_boost
        counts_raw[label or "neutral"] += 1
    institutional_articles = Article.query.filter_by(event_id=event_id, source_layer="institutional").all()
    institutional = len(institutional_articles)
    total = len(comments)
    word_counts = Counter()
    demand_counts = Counter()
    stopwords = {"这个", "那个", "我们", "你们", "他们", "就是", "还是", "没有", "一个", "什么", "怎么"}
    for item in comments:
        text = item.content or ""
        try:
            import jieba
            words = jieba.lcut(text)
        except Exception:
            words = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
        word_counts.update(word for word in words if len(word.strip()) >= 2 and word not in stopwords)
        for marker, label in (("希望", "希望改善"), ("应该", "要求处置"), ("投诉", "投诉问责"), ("回应", "要求回应"), ("救援", "救援需求"), ("赔偿", "赔偿需求")):
            if marker in text: demand_counts[label] += 1
    official_words = Counter()
    response_articles = 0
    for article in institutional_articles:
        text = " ".join((article.title or "", article.clean_content or ""))
        if any(marker in text for marker in ("回应", "通报", "处置", "调查", "救援", "转移", "保障")):
            response_articles += 1
        try:
            import jieba
            official_words.update(word for word in jieba.lcut(text[:2000]) if len(word.strip()) >= 2 and word not in stopwords)
        except Exception:
            pass
    response_rate = response_articles / institutional if institutional else None
    negative_rate = counts["negative"] / total if total else None
    gap_score = round(max(0.0, negative_rate - response_rate) * 100, 2) if negative_rate is not None and response_rate is not None else None
    # 加权分布归一化
    total_weight = sum(counts.values())
    weighted_dist = {k: round(counts[k] / total_weight, 4) if total_weight else 0 for k in ("positive", "neutral", "negative")}
    raw_total = sum(counts_raw.values())
    raw_dist = {k: counts_raw[k] for k in ("positive", "neutral", "negative")}
    negative_rate_w = weighted_dist.get("negative", 0)
    return {
        "comment_count": total,
        "sentiment_distribution": raw_dist,  # 原始计数（兼容旧接口）
        "weighted_sentiment": weighted_dist,  # 质量加权分布
        "negative_rate": negative_rate_w,
        "sentiment_corrected_count": corrected_count,  # 被规则校正的评论数
        "institutional_article_count": institutional,
        "analysis_mode": "narrative_gap" if institutional and total else "public_opinion_only" if total else "insufficient_data",
        "narrative_gap_available": bool(institutional and total),
        "coverage_warning": None if institutional else "INSTITUTIONAL_DATA_NOT_COLLECTED",
        "public_keywords": [{"word": word, "count": count} for word, count in word_counts.most_common(10)],
        "public_demands": [{"demand": word, "count": count} for word, count in demand_counts.most_common(8)],
        "opinion_divergence": round(1 - (max(counts.values()) / total_weight), 4) if total_weight else None,
        "official_keywords": [{"word": word, "count": count} for word, count in official_words.most_common(10)],
        "institutional_response_rate": response_rate,
        "narrative_gap_score": gap_score,
        "gap_interpretation": ("公众负面情绪高于机构回应覆盖" if gap_score is not None and gap_score >= 20 else "机构回应与公众情绪偏差有限" if gap_score is not None else None),
    }
