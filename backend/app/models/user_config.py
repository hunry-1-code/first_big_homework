from app.extensions import db


class UserConfig(db.Model):
    __tablename__ = "user_config"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    followed_sources = db.Column(db.JSON)
    keywords = db.Column(db.JSON)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

