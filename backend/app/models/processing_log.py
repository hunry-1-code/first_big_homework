from app.extensions import db


class ProcessingLog(db.Model):
    __tablename__ = "processing_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True, index=True)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False, index=True)
    snapshot_id = db.Column(db.BigInteger, nullable=True)
    stage = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    error_code = db.Column(db.String(80), nullable=True)
    message = db.Column(db.Text)
    retryable = db.Column(db.Boolean, default=False)
    duration_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
