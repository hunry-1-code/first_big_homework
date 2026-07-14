from collections import Counter
import re
from app.models import Article, Comment

NEGATIVE = ("不满", "没人管", "失望", "愤怒", "质疑", "投诉", "糟糕", "骗人")
POSITIVE = ("支持", "感谢", "点赞", "辛苦", "很好", "加油")

def get_public_opinion_snapshot(event_id: int) -> dict:
    article_ids = [row[0] for row in Article.query.with_entities(Article.id).filter_by(event_id=event_id).all()]
    comments = Comment.query.filter(Comment.article_id.in_(article_ids)).all() if article_ids else []
    counts = Counter()
    for item in comments:
        text = item.content or ""
        label = item.sentiment_label
        if not label:
            label = "negative" if any(x in text for x in NEGATIVE) else "positive" if any(x in text for x in POSITIVE) else "neutral"
        counts[label] += 1
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
    return {
        "comment_count": total,
        "sentiment_distribution": {key: counts[key] for key in ("positive", "neutral", "negative")},
        "negative_rate": negative_rate,
        "institutional_article_count": institutional,
        "analysis_mode": "narrative_gap" if institutional and total else "public_opinion_only" if total else "insufficient_data",
        "narrative_gap_available": bool(institutional and total),
        "coverage_warning": None if institutional else "INSTITUTIONAL_DATA_NOT_COLLECTED",
        "public_keywords": [{"word": word, "count": count} for word, count in word_counts.most_common(10)],
        "public_demands": [{"demand": word, "count": count} for word, count in demand_counts.most_common(8)],
        "opinion_divergence": round(1 - (max(counts.values()) / total), 4) if total else None,
        "official_keywords": [{"word": word, "count": count} for word, count in official_words.most_common(10)],
        "institutional_response_rate": response_rate,
        "narrative_gap_score": gap_score,
        "gap_interpretation": ("公众负面情绪高于机构回应覆盖" if gap_score is not None and gap_score >= 20 else "机构回应与公众情绪偏差有限" if gap_score is not None else None),
    }
