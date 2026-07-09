from app.extensions import db


class Article(db.Model):
    __tablename__ = "article"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=True)
    platform = db.Column(db.String(50), nullable=False)
    url = db.Column(db.String(500), unique=True, nullable=False)
    title = db.Column(db.String(500), nullable=False)
    raw_content = db.Column(db.Text)
    clean_content = db.Column(db.Text)
    raw_json = db.Column(db.JSON)
    clean_status = db.Column(db.String(20), default="pending")
    clean_error = db.Column(db.Text)
    author = db.Column(db.String(100))
    author_followers = db.Column(db.Integer, default=0)
    author_verified = db.Column(db.Boolean, default=False)
    author_type = db.Column(db.String(50))
    publish_time = db.Column(db.DateTime, nullable=False)
    comments_count = db.Column(db.Integer, default=0)
    reposts_count = db.Column(db.Integer, default=0)
    likes_count = db.Column(db.Integer, default=0)
    sentiment_label = db.Column(db.String(10))
    sentiment_score = db.Column(db.Float)
    sentiment_reason = db.Column(db.Text)
    sentiment_method = db.Column(db.String(20))
    is_suspicious = db.Column(db.Boolean, default=False)
    suspicious_score = db.Column(db.Float)
    suspicious_reason = db.Column(db.Text)
    suspicious_method = db.Column(db.String(20))
    tfidf_vector = db.Column(db.JSON)
    crawled_at = db.Column(db.DateTime, server_default=db.func.now())

