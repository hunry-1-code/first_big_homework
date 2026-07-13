from app.extensions import db


class DailyHotRun(db.Model):
    __tablename__ = "daily_hot_run"
    __table_args__ = (
        db.UniqueConstraint(
            "run_date",
            "config_hash",
            name="uq_daily_hot_run_date_config",
        ),
        db.Index("ix_daily_hot_run_status_created", "status", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    run_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    available_sources = db.Column(db.JSON)
    failed_sources = db.Column(db.JSON)
    errors = db.Column(db.JSON)
    item_count = db.Column(db.Integer, nullable=False, default=0)
    config_hash = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    completed_at = db.Column(db.DateTime)


class DailyHotItem(db.Model):
    __tablename__ = "daily_hot_item"
    __table_args__ = (
        db.UniqueConstraint(
            "run_id",
            "normalized_key",
            name="uq_daily_hot_item_run_key",
        ),
        db.UniqueConstraint(
            "run_id",
            "rank",
            name="uq_daily_hot_item_run_rank",
        ),
        db.Index(
            "ix_daily_hot_item_enrichment",
            "enrichment_status",
            "last_seen_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    run_id = db.Column(
        db.Integer,
        db.ForeignKey("daily_hot_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    normalized_key = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    fused_score = db.Column(db.Float, nullable=False)
    rank = db.Column(db.Integer, nullable=False)
    source_ranks = db.Column(db.JSON)
    source_payloads = db.Column(db.JSON)
    first_seen_at = db.Column(db.DateTime, nullable=False)
    last_seen_at = db.Column(db.DateTime, nullable=False)
    enrichment_status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
    )
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=True)
    analysis_task_id = db.Column(
        db.Integer,
        db.ForeignKey("task.id"),
        nullable=True,
    )
    error_code = db.Column(db.String(64))
    error_message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

