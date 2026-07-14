from app.extensions import db

class Comment(db.Model):
    __tablename__ = "comment"
    __table_args__ = (db.UniqueConstraint("platform", "source_comment_id", name="uq_comment_platform_source_id"),)
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False, index=True)
    parent_comment_id = db.Column(db.Integer, db.ForeignKey("comment.id"), nullable=True, index=True)
    platform = db.Column(db.String(50), nullable=False)
    source_comment_id = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    content_hash = db.Column(db.String(64), nullable=False, index=True)
    content_kind = db.Column(db.String(20), nullable=False, default="comment")
    author = db.Column(db.String(255))
    likes_count = db.Column(db.BigInteger, default=0)
    replies_count = db.Column(db.BigInteger, default=0)
    sentiment_label = db.Column(db.String(20))
    sentiment_score = db.Column(db.Float)
    analysis_status = db.Column(db.String(20), default="pending", index=True)
    raw_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
