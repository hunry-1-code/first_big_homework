from app.extensions import db


class QaHistory(db.Model):
    __tablename__ = "qa_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

