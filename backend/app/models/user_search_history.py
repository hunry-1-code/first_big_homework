from app.extensions import db


class UserSearchHistory(db.Model):
    __tablename__ = "user_search_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    keyword = db.Column(db.String(255), nullable=False, index=True)
    platforms = db.Column(db.JSON, nullable=False)
    target_count = db.Column(db.Integer, nullable=False, default=50)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)
