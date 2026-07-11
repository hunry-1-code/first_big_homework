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
        db.BigInteger,
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
    current_sentiment_snapshot_id = db.Column(db.BigInteger, nullable=True, index=True)
    sentiment_score = db.Column(db.Float, default=0)
    sentiment_updated_at = db.Column(db.DateTime)
    lifecycle_stage = db.Column(db.String(20), default="潜伏期")
    center_vector = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
