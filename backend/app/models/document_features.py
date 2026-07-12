from app.extensions import db


SQLITE_BIGINT = db.BigInteger().with_variant(db.Integer, "sqlite")


class DocumentFeatures(db.Model):
    __tablename__ = "document_features"

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False, unique=True)
    tokens = db.Column(db.JSON)
    tfidf_tokens = db.Column(db.JSON)
    sentiment_tokens = db.Column(db.JSON)
    topics = db.Column(db.JSON)
    mentions = db.Column(db.JSON)
    tfidf_vector = db.Column(db.JSON)
    segment_version = db.Column(db.String(20))
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
