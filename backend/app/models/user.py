from app.extensions import db


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nickname = db.Column(db.String(50))
    role = db.Column(db.String(20), default="user")
    status = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

