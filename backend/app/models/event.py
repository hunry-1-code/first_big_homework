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
    sentiment_positive = db.Column(db.Float, default=0)
    sentiment_negative = db.Column(db.Float, default=0)
    sentiment_neutral = db.Column(db.Float, default=0)
    lifecycle_stage = db.Column(db.String(20), default="潜伏期")
    center_vector = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

