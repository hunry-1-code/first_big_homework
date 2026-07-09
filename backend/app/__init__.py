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

    @app.get("/api/health")
    def health():
        return ok({"status": "ok", "service": "opinion-analysis-backend"})

    return app
