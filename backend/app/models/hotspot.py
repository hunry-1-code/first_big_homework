from app.extensions import db


SQLITE_BIGINT = db.BigInteger().with_variant(db.Integer, "sqlite")


class HotspotRun(db.Model):
    __tablename__ = "hotspot_run"
    __table_args__ = (
        db.UniqueConstraint(
            "analysis_run_id",
            "config_hash",
            "scope",
            "mode",
            "attempt",
            name="uq_hotspot_run_fingerprint",
        ),
        db.Index("ix_hotspot_run_status_created", "status", "created_at"),
        db.Index("ix_hotspot_run_user_created", "user_id", "created_at"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    analysis_run_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("analysis_run.id"), nullable=False, index=True
    )
    source_task_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("task.id"), nullable=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    mode = db.Column(db.String(20), nullable=False, default="hot")
    scope = db.Column(db.String(20), nullable=False, default="global")
    attempt = db.Column(db.Integer, nullable=False, default=1)
    window_start = db.Column(db.DateTime, nullable=True)
    window_end = db.Column(db.DateTime, nullable=True)
    dataset_hash = db.Column(db.String(64), nullable=False, index=True)
    config_hash = db.Column(db.String(64), nullable=False, index=True)
    lda_config = db.Column(db.JSON)
    selected_k = db.Column(db.Integer)
    metrics = db.Column(db.JSON)
    versions = db.Column(db.JSON)
    status = db.Column(db.String(20), nullable=False, default="pending")
    topic_status = db.Column(db.String(20), nullable=False, default="pending")
    heat_status = db.Column(db.String(20), nullable=False, default="pending")
    warnings = db.Column(db.JSON)
    error_code = db.Column(db.String(64))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)


class HotSeedExpansion(db.Model):
    __tablename__ = "hot_seed_expansion"
    __table_args__ = (
        db.UniqueConstraint(
            "seed_article_id",
            "query",
            "article_id",
            name="uq_hot_seed_expansion_seed_query_article",
        ),
        db.Index("ix_hot_seed_expansion_article", "article_id"),
        db.Index(
            "ix_hot_seed_expansion_seed_query", "seed_article_id", "query"
        ),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    seed_article_id = db.Column(
        db.Integer, db.ForeignKey("article.id"), nullable=False
    )
    search_query = db.Column("query", db.String(255), nullable=False)
    crawl_task_id = db.Column(
        SQLITE_BIGINT, db.ForeignKey("task.id"), nullable=True
    )
    platform = db.Column(db.String(50), nullable=False)
    article_id = db.Column(
        db.Integer, db.ForeignKey("article.id"), nullable=False
    )
    source_rank = db.Column(db.Integer, nullable=True)
    discovered_at = db.Column(db.DateTime, nullable=False)


class TopicResult(db.Model):
    __tablename__ = "topic_result"
    __table_args__ = (
        db.UniqueConstraint(
            "hotspot_run_id", "topic_index", name="uq_topic_result_run_index"
        ),
        db.Index("ix_topic_result_run_category", "hotspot_run_id", "category"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    hotspot_run_id = db.Column(
        SQLITE_BIGINT,
        db.ForeignKey("hotspot_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_index = db.Column(db.Integer, nullable=False)
    keywords = db.Column(db.JSON)
    category = db.Column(db.String(30), nullable=False, default="其他")
    topic_name = db.Column(db.String(100), nullable=False)
    naming_method = db.Column(db.String(40), nullable=False)
    naming_confidence = db.Column(db.Float, nullable=False, default=0.0)
    document_count = db.Column(db.Integer, nullable=False, default=0)
    probability_mass = db.Column(db.Float, nullable=False, default=0.0)
    topic_signature = db.Column(db.String(64), nullable=False, index=True)
    warnings = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class TopicArticleAssignment(db.Model):
    __tablename__ = "topic_article_assignment"
    __table_args__ = (
        db.UniqueConstraint(
            "hotspot_run_id",
            "topic_result_id",
            "article_id",
            name="uq_topic_assignment_run_topic_article",
        ),
        db.Index(
            "ix_topic_assignment_run_article",
            "hotspot_run_id",
            "article_id",
        ),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    hotspot_run_id = db.Column(
        SQLITE_BIGINT,
        db.ForeignKey("hotspot_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_result_id = db.Column(
        SQLITE_BIGINT,
        db.ForeignKey("topic_result.id", ondelete="CASCADE"),
        nullable=False,
    )
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False)
    content_identity = db.Column(db.String(80), nullable=False)
    probability = db.Column(db.Float, nullable=False)
    probabilities = db.Column(db.JSON)
    is_primary = db.Column(db.Boolean, nullable=False, default=True)
    warnings = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class EventHeatSnapshot(db.Model):
    __tablename__ = "event_heat_snapshot"
    __table_args__ = (
        db.UniqueConstraint(
            "hotspot_run_id", "event_id", name="uq_event_heat_run_event"
        ),
        db.Index("ix_event_heat_event_calculated", "event_id", "calculated_at"),
        db.Index("ix_event_heat_hot_rank", "eligible_as_hot", "rank"),
    )

    id = db.Column(SQLITE_BIGINT, primary_key=True, autoincrement=True)
    hotspot_run_id = db.Column(
        SQLITE_BIGINT,
        db.ForeignKey("hotspot_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    calculated_at = db.Column(db.DateTime, nullable=False)
    raw_statistics = db.Column(db.JSON)
    component_scores = db.Column(db.JSON)
    core_heat = db.Column(db.Float, nullable=False)
    spread_heat = db.Column(db.Float, nullable=True)
    final_heat = db.Column(db.Float, nullable=False)
    eligible_as_hot = db.Column(db.Boolean, nullable=False, default=False)
    rank = db.Column(db.Integer, nullable=True)
    status_change = db.Column(db.String(20), nullable=True)
    time_confidence = db.Column(db.String(20), nullable=False, default="low")
    formula_version = db.Column(db.String(30), nullable=False, default="v1")
    calculation_details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
