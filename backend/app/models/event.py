from app.extensions import db


class Event(db.Model):
    __tablename__ = "event"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text)
    time_code = db.Column(db.String(50))
    location = db.Column(db.String(100))
    cause = db.Column(db.String(500))
    key_figures = db.Column(db.String(500))
    heat_index = db.Column(db.Float, default=0)
    current_heat_snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "event_heat_snapshot.id",
            name="fk_event_current_heat_snapshot",
            use_alter=True,
        ),
        nullable=True,
    )
    core_heat = db.Column(db.Float, default=0)
    spread_heat = db.Column(db.Float, nullable=True)
    is_hot = db.Column(db.Boolean, nullable=False, default=False)
    hot_rank = db.Column(db.Integer, nullable=True)
    topic_category = db.Column(db.String(30), nullable=True)
    topic_name = db.Column(db.String(100), nullable=True)
    first_publish_time = db.Column(db.DateTime, nullable=True)
    last_activity_time = db.Column(db.DateTime, nullable=True)
    independent_report_count = db.Column(db.Integer, nullable=False, default=0)
    platform_count = db.Column(db.Integer, nullable=False, default=0)
    time_confidence = db.Column(db.String(20), nullable=False, default="low")
    sentiment_positive = db.Column(db.Float, default=0)
    sentiment_negative = db.Column(db.Float, default=0)
    sentiment_neutral = db.Column(db.Float, default=0)
    current_sentiment_snapshot_id = db.Column(db.Integer, nullable=True, index=True)
    sentiment_score = db.Column(db.Float, default=0)
    sentiment_updated_at = db.Column(db.DateTime)
    lifecycle_stage = db.Column(db.String(20), default="潜伏期")
    lifecycle_status = db.Column(
        db.String(24), nullable=False, default="data_insufficient"
    )
    lifecycle_confidence = db.Column(db.Float, nullable=False, default=0.0)
    lifecycle_evidence = db.Column(db.JSON)
    lifecycle_updated_at = db.Column(db.DateTime)
    metadata_status = db.Column(db.String(24), nullable=False, default="pending")
    metadata_version = db.Column(db.String(32))
    metadata_confidence = db.Column(db.Float, nullable=False, default=0.0)
    metadata_evidence = db.Column(db.JSON)
    metadata_updated_at = db.Column(db.DateTime)
    source = db.Column(db.String(20), nullable=False, default="search")  # search / daily_hot / manual
    search_keyword = db.Column(db.String(255), nullable=True, index=True)  # 来源搜索关键词
    source_task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True, index=True)  # 来源爬取任务
    ttl_days = db.Column(db.Integer, nullable=True)  # 热点事件 7 天过期，搜索事件 null=永久
    center_vector = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
