import hashlib
from app.extensions import db
from app.models import Comment
from app.crawler.comments import RawComment
from app.analysis.sentiment_analyzer import analyze_with_snownlp

def persist_comment(article, raw: RawComment) -> Comment:
    text = " ".join((raw.content or "").split())
    if not text:
        raise ValueError("comment content is empty")
    row = Comment.query.filter_by(platform=raw.platform, source_comment_id=str(raw.source_comment_id)).first()
    if row is None:
        row = Comment(article_id=article.id, platform=raw.platform, source_comment_id=str(raw.source_comment_id), content_hash=hashlib.sha256(text.encode()).hexdigest())
        db.session.add(row)
    row.article_id = article.id; row.content = text; row.author = raw.author
    if raw.parent_source_comment_id:
        parent = Comment.query.filter_by(platform=raw.platform, source_comment_id=str(raw.parent_source_comment_id)).first()
        row.parent_comment_id = parent.id if parent else None
    row.likes_count = raw.likes_count or 0; row.replies_count = raw.replies_count or 0
    row.content_kind = raw.content_kind; row.raw_json = raw.raw_json
    try:
        sentiment = analyze_with_snownlp(text)
        row.sentiment_label = sentiment["label"]
        row.sentiment_score = sentiment["score"]
        row.analysis_status = "success"
    except Exception:
        row.analysis_status = "fallback"
        row.sentiment_label = "negative" if any(word in text for word in ("不满", "失望", "没人管", "投诉", "愤怒")) else "neutral"
        row.sentiment_score = -0.5 if row.sentiment_label == "negative" else 0.0
    db.session.commit()
    return row
