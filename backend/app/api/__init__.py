from flask import Flask

from app.api.auth import auth_bp
from app.api.crawler import crawler_bp
from app.api.events import events_bp
from app.api.import_data import import_bp
from app.api.qa import qa_bp
from app.api.reports import reports_bp
from app.api.tasks import tasks_bp
from app.api.user import user_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(events_bp, url_prefix="/api/events")
    app.register_blueprint(reports_bp, url_prefix="/api/events")
    app.register_blueprint(qa_bp, url_prefix="/api/qa")
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(crawler_bp, url_prefix="/api/crawler")
    app.register_blueprint(import_bp, url_prefix="/api/import")
    app.register_blueprint(tasks_bp, url_prefix="/api/tasks")

