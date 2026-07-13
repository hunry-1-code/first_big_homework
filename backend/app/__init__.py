from __future__ import annotations


def create_app(config_object=None):
    from flask import Flask
    from flask_cors import CORS

    from app.api import register_blueprints
    from app.core.config import Config
    from app.core.response import ok
    from app.extensions import db

    if config_object is None:
        config_object = Config

    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGINS"]}},
        allow_headers=["Content-Type", "Authorization"],
    )

    register_blueprints(app)

    if app.config.get("AUTO_CREATE_DB", False):
        with app.app_context():
            db.create_all()
            # SQLite WAL 模式：允许并发读写，解决 APScheduler 与 publish 的锁竞争
            from sqlalchemy import text
            try:
                db.session.execute(text("PRAGMA journal_mode=WAL"))
                db.session.commit()
            except Exception:
                pass

    if app.config.get("TASK_RECOVER_ON_STARTUP", False):
        from sqlalchemy import inspect
        from sqlalchemy.exc import SQLAlchemyError

        from app.tasks.runner import recover_background_jobs, start_recovery_scheduler

        try:
            with app.app_context():
                task_table_exists = inspect(db.engine).has_table("task")
            if task_table_exists:
                recover_background_jobs(app)
                start_recovery_scheduler(app)
        except SQLAlchemyError as exc:
            app.logger.warning("后台任务恢复检查失败: %s", exc)

    @app.get("/api/health")
    def health():
        return ok({"status": "ok", "service": "opinion-analysis-backend"})

    return app
