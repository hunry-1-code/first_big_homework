from app.extensions import db



class ArticleEmbedding(db.Model):
    __tablename__ = "article_embedding"
    __table_args__ = (
        db.UniqueConstraint(
            "article_id",
            "content_identity",
            "model_name",
            "model_version",
            "preprocess_version",
            name="uq_article_embedding_version",
        ),
        db.Index(
            "ix_article_embedding_lookup",
            "article_id",
            "model_name",
            "model_version",
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False)
    article_snapshot_id = db.Column(
        db.Integer, db.ForeignKey("article_snapshot.id"), nullable=True
    )
    content_version = db.Column(db.Integer, nullable=False, default=1)
    content_identity = db.Column(db.String(80), nullable=False)
    model_name = db.Column(db.String(255), nullable=False)
    model_version = db.Column(db.String(64), nullable=False, default="default")
    preprocess_version = db.Column(db.String(64), nullable=False, default="v1")
    dimension = db.Column(db.Integer, nullable=False)
    vector = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

