from app.extensions import db


class AnalysisRun(db.Model):
    __tablename__ = "analysis_run"
    __table_args__ = (
        db.Index("ix_analysis_run_user_created", "user_id", "created_at"),
        db.Index("ix_analysis_run_status", "status"),
        db.Index("ix_analysis_run_fingerprint", "query_fingerprint", "dataset_hash"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    source_task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    mode = db.Column(db.String(20), nullable=False, default="search")
    keyword = db.Column(db.String(255))
    platforms = db.Column(db.JSON)
    query_fingerprint = db.Column(db.String(64), nullable=False, index=True)
    dataset_hash = db.Column(db.String(64), nullable=False, index=True)
    config_hash = db.Column(db.String(64), nullable=False, index=True)
    article_count = db.Column(db.Integer, nullable=False, default=0)
    representative_count = db.Column(db.Integer, nullable=False, default=0)
    tfidf_config = db.Column(db.JSON)
    versions = db.Column(db.JSON)
    statistics = db.Column(db.JSON)
    status = db.Column(db.String(20), nullable=False, default="pending")
    warnings = db.Column(db.JSON)
    error_code = db.Column(db.String(64))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)


class AnalysisRunArticle(db.Model):
    __tablename__ = "analysis_run_article"
    __table_args__ = (
        db.UniqueConstraint(
            "analysis_run_id", "article_id", name="uq_analysis_run_article"
        ),
        db.Index("ix_analysis_run_article_run_status", "analysis_run_id", "feature_status"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    analysis_run_id = db.Column(
        db.Integer,
        db.ForeignKey("analysis_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False)
    article_snapshot_id = db.Column(
        db.Integer, db.ForeignKey("article_snapshot.id"), nullable=True
    )
    content_version = db.Column(db.Integer, nullable=False, default=1)
    content_identity = db.Column(db.String(80), nullable=False)
    is_representative = db.Column(db.Boolean, nullable=False, default=False)
    nlp_weight = db.Column(db.Float, nullable=False, default=1.0)
    feature_status = db.Column(db.String(30), nullable=False, default="pending")
    keywords = db.Column(db.JSON)
    warnings = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

