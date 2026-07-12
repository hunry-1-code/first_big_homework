from app.extensions import db


SQLITE_BIGINT = db.BigInteger().with_variant(db.Integer, "sqlite")


class SentimentRun(db.Model):
    __tablename__ = "sentiment_run"
    __table_args__ = (
        db.UniqueConstraint(
            "aggregation_run_id",
            "scope",
            "mode",
            "config_hash",
            "attempt",
            name="uq_sentiment_run_fingerprint",
        ),
        db.Index("ix_sentiment_run_status_created", "status", "created_at"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    aggregation_run_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("aggregation_run.id"), nullable=False, index=True
    )
    source_task_id = db.Column(SQLITE_BIGINT, db.ForeignKey("task.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    scope = db.Column(db.String(24), nullable=False)
    mode = db.Column(db.String(20), nullable=False)
    attempt = db.Column(db.Integer, nullable=False, default=1)
    dataset_hash = db.Column(db.String(64), nullable=False, index=True)
    config_hash = db.Column(db.String(64), nullable=False, index=True)
    config = db.Column(db.JSON)
    versions = db.Column(db.JSON)
    statistics = db.Column(db.JSON)
    status = db.Column(db.String(20), nullable=False, default="pending")
    warnings = db.Column(db.JSON)
    error_code = db.Column(db.String(64))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)


class ArticleSentimentResult(db.Model):
    __tablename__ = "article_sentiment_result"
    __table_args__ = (
        db.UniqueConstraint(
            "sentiment_run_id", "article_id", name="uq_article_sentiment_run_article"
        ),
        db.Index("ix_article_sentiment_cache", "article_id", "content_identity"),
        db.Index("ix_article_sentiment_event", "event_id"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    sentiment_run_id = db.Column(
        SQLITE_BIGINT,
        db.ForeignKey("sentiment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False)
    content_identity = db.Column(db.String(80), nullable=False)
    aggregation_cluster_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("aggregation_cluster.id"), nullable=True
    )
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=True)
    label = db.Column(db.String(16), nullable=False)
    score = db.Column(db.Float, nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    dimension = db.Column(db.String(16), nullable=False)
    target = db.Column(db.String(200), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    method = db.Column(db.String(24), nullable=False)
    model_name = db.Column(db.String(255))
    model_version = db.Column(db.String(64))
    prompt_version = db.Column(db.String(64), nullable=False)
    preprocess_version = db.Column(db.String(64), nullable=False)
    raw_response = db.Column(db.JSON)
    inherited_from_result_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("article_sentiment_result.id"), nullable=True
    )
    weight_details = db.Column(db.JSON)
    warnings = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class EventSentimentSnapshot(db.Model):
    __tablename__ = "event_sentiment_snapshot"
    __table_args__ = (
        db.UniqueConstraint(
            "sentiment_run_id", "event_id", name="uq_sentiment_snapshot_run_event"
        ),
        db.UniqueConstraint(
            "sentiment_run_id",
            "aggregation_cluster_id",
            name="uq_sentiment_snapshot_run_cluster",
        ),
        db.Index("ix_sentiment_snapshot_event_time", "event_id", "calculated_at"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    sentiment_run_id = db.Column(
        SQLITE_BIGINT,
        db.ForeignKey("sentiment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=True)
    aggregation_cluster_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("aggregation_cluster.id"), nullable=True
    )
    calculated_at = db.Column(db.DateTime, nullable=False)
    article_count = db.Column(db.Integer, nullable=False, default=0)
    representative_count = db.Column(db.Integer, nullable=False, default=0)
    raw_counts = db.Column(db.JSON)
    weighted_ratios = db.Column(db.JSON)
    dominant_label = db.Column(db.String(16))
    average_score = db.Column(db.Float, nullable=False, default=0.0)
    daily_trend = db.Column(db.JSON)
    platform_distribution = db.Column(db.JSON)
    time_confidence = db.Column(db.String(20), nullable=False, default="low")
    calculation_details = db.Column(db.JSON)
    algorithm_version = db.Column(db.String(64), nullable=False)
    warnings = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


__all__ = ["ArticleSentimentResult", "EventSentimentSnapshot", "SentimentRun"]
