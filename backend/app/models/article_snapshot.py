from app.extensions import db
from sqlalchemy.dialects.mysql import LONGTEXT


LONG_TEXT = db.Text().with_variant(LONGTEXT(), "mysql")


class ArticleSnapshot(db.Model):
    __tablename__ = "article_snapshot"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False, index=True)
    crawled_at = db.Column(db.DateTime, server_default=db.func.now())
    http_status = db.Column(db.Integer, nullable=True)
    fetch_status = db.Column(db.String(20), nullable=False)
    content_hash = db.Column(db.String(64), nullable=True)
    raw_content = db.Column(LONG_TEXT, nullable=True)
    raw_json = db.Column(db.JSON, nullable=True)
    comments_count = db.Column(db.BigInteger, nullable=True)
    reposts_count = db.Column(db.BigInteger, nullable=True)
    likes_count = db.Column(db.BigInteger, nullable=True)
    views_count = db.Column(db.BigInteger, nullable=True)
    fetch_error = db.Column(db.Text, nullable=True)
