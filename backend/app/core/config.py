import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_EXPIRES_DELTA = timedelta(hours=int(os.getenv("JWT_EXPIRES_HOURS", "24")))

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///opinion_analysis_dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    FRONTEND_ORIGINS = [
        origin.strip()
        for origin in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    DEMO_ADMIN_USERNAME = os.getenv("DEMO_ADMIN_USERNAME", "admin")
    DEMO_ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "admin123")

    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-chat")

