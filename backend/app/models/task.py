from app.extensions import db


class Task(db.Model):
    __tablename__ = "task"

    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="pending")
    progress = db.Column(db.Integer, default=0)
    message = db.Column(db.Text)
    payload = db.Column(db.JSON)
    result = db.Column(db.JSON)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    started_at = db.Column(db.DateTime)
    heartbeat_at = db.Column(db.DateTime)
    lease_token = db.Column(db.String(64))
    attempt = db.Column(db.Integer, nullable=False, default=0)
    finished_at = db.Column(db.DateTime)
