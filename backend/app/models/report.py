from app.extensions import db


class Report(db.Model):
    __tablename__ = "report"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    overview_text = db.Column(db.Text)
    trend_data = db.Column(db.JSON)
    sentiment_data = db.Column(db.JSON)
    platform_data = db.Column(db.JSON)
    keywords_data = db.Column(db.JSON)
    lifecycle_data = db.Column(db.JSON)
    risk_data = db.Column(db.JSON)
    generated_at = db.Column(db.DateTime, server_default=db.func.now())

