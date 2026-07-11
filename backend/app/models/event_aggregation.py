from app.extensions import db


SQLITE_BIGINT = db.BigInteger().with_variant(db.Integer, "sqlite")


class AggregationRun(db.Model):
    __tablename__ = "aggregation_run"
    __table_args__ = (
        db.UniqueConstraint(
            "analysis_run_id",
            "hotspot_run_id",
            "scope",
            "mode",
            "config_hash",
            "attempt",
            name="uq_aggregation_run_fingerprint",
        ),
        db.Index("ix_aggregation_run_status_created", "status", "created_at"),
        db.Index("ix_aggregation_run_query_cache", "query_fingerprint", "cache_expires_at"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    analysis_run_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("analysis_run.id"), nullable=False, index=True
    )
    hotspot_run_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("hotspot_run.id"), nullable=True, index=True
    )
    source_task_id = db.Column(SQLITE_BIGINT, db.ForeignKey("task.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    scope = db.Column(db.String(24), nullable=False)
    mode = db.Column(db.String(20), nullable=False)
    attempt = db.Column(db.Integer, nullable=False, default=1)
    query_fingerprint = db.Column(db.String(64), nullable=True, index=True)
    dataset_hash = db.Column(db.String(64), nullable=False, index=True)
    config_hash = db.Column(db.String(64), nullable=False, index=True)
    config = db.Column(db.JSON)
    versions = db.Column(db.JSON)
    statistics = db.Column(db.JSON)
    status = db.Column(db.String(20), nullable=False, default="pending")
    warnings = db.Column(db.JSON)
    error_code = db.Column(db.String(64))
    error_message = db.Column(db.Text)
    cache_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)


class AggregationCluster(db.Model):
    __tablename__ = "aggregation_cluster"
    __table_args__ = (
        db.UniqueConstraint(
            "aggregation_run_id", "cluster_index", name="uq_aggregation_cluster_run_index"
        ),
        db.Index("ix_aggregation_cluster_event", "resolved_event_id"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    aggregation_run_id = db.Column(
        SQLITE_BIGINT,
        db.ForeignKey("aggregation_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    cluster_index = db.Column(db.Integer, nullable=False)
    resolved_event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=True)
    title = db.Column(db.String(500), nullable=False)
    topic_category = db.Column(db.String(30))
    topic_name = db.Column(db.String(100))
    keywords = db.Column(db.JSON)
    entities = db.Column(db.JSON)
    first_publish_time = db.Column(db.DateTime)
    last_activity_time = db.Column(db.DateTime)
    representative_article_id = db.Column(db.Integer, db.ForeignKey("article.id"))
    member_count = db.Column(db.Integer, nullable=False, default=0)
    platform_count = db.Column(db.Integer, nullable=False, default=0)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class AggregationAssignment(db.Model):
    __tablename__ = "aggregation_assignment"
    __table_args__ = (
        db.UniqueConstraint(
            "aggregation_run_id", "article_id", name="uq_aggregation_assignment_run_article"
        ),
        db.Index("ix_aggregation_assignment_event", "resolved_event_id"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    aggregation_run_id = db.Column(
        SQLITE_BIGINT,
        db.ForeignKey("aggregation_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    aggregation_cluster_id = db.Column(
        SQLITE_BIGINT,
        db.ForeignKey("aggregation_cluster.id", ondelete="CASCADE"),
        nullable=True,
    )
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False)
    content_identity = db.Column(db.String(80), nullable=False)
    resolved_event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=True)
    membership_action = db.Column(db.String(24), nullable=False)
    candidate_event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=True)
    similarity = db.Column(db.Float, nullable=False, default=0.0)
    score_details = db.Column(db.JSON)
    decision_reason = db.Column(db.JSON)
    is_representative = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class EventArticleMembership(db.Model):
    __tablename__ = "event_article_membership"
    __table_args__ = (
        db.UniqueConstraint("active_article_id", name="uq_event_membership_active_article"),
        db.Index("ix_event_membership_event_active", "event_id", "is_active"),
        db.Index("ix_event_membership_article", "article_id"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False)
    active_article_id = db.Column(db.Integer, nullable=True)
    source_aggregation_run_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("aggregation_run.id"), nullable=False
    )
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    decision_method = db.Column(db.String(64), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    valid_from = db.Column(db.DateTime, nullable=False)
    valid_to = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class EventRepresentation(db.Model):
    __tablename__ = "event_representation"
    __table_args__ = (
        db.UniqueConstraint(
            "event_id",
            "model_name",
            "model_version",
            "preprocess_version",
            name="uq_event_representation_version",
        ),
        db.Index("ix_event_representation_model", "model_name", "model_version"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    model_name = db.Column(db.String(255), nullable=False)
    model_version = db.Column(db.String(64), nullable=False)
    preprocess_version = db.Column(db.String(64), nullable=False)
    dimension = db.Column(db.Integer, nullable=False)
    vector = db.Column(db.JSON, nullable=False)
    keywords = db.Column(db.JSON)
    entities = db.Column(db.JSON)
    member_count = db.Column(db.Integer, nullable=False, default=0)
    source_aggregation_run_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("aggregation_run.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())


class EventMergeRecord(db.Model):
    __tablename__ = "event_merge_record"
    __table_args__ = (
        db.UniqueConstraint(
            "source_event_id", "target_event_id", "status", name="uq_event_merge_pair_status"
        ),
        db.Index("ix_event_merge_status_created", "status", "created_at"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    source_event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    target_event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    aggregation_run_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("aggregation_run.id"), nullable=True
    )
    similarity_evidence = db.Column(db.JSON)
    reason = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default="pending")
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


__all__ = [
    "AggregationAssignment",
    "AggregationCluster",
    "AggregationRun",
    "EventArticleMembership",
    "EventMergeRecord",
    "EventRepresentation",
]
