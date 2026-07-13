from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Config
from app.extensions import db
from app.models import DailyHotItem, DailyHotRun


SQL_PATH = Path(__file__).with_name("20260713_daily_hot.sql")


def _statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    return [item.strip() for item in "\n".join(lines).split(";") if item.strip()]


def migrate(database_url: str, *, sql_path: Path = SQL_PATH) -> None:
    engine = create_engine(database_url)
    if engine.dialect.name == "sqlite":
        db.metadata.create_all(
            engine,
            tables=[DailyHotRun.__table__, DailyHotItem.__table__],
        )
        engine.dispose()
        return
    if engine.dialect.name != "mysql":
        engine.dispose()
        raise ValueError("This migration targets SQLite or MySQL 8.")
    with engine.begin() as connection:
        for statement in _statements(sql_path.read_text(encoding="utf-8")):
            connection.execute(text(statement))
    engine.dispose()


def run_migration(database_url: str) -> None:
    migrate(database_url)


if __name__ == "__main__":
    run_migration(Config.SQLALCHEMY_DATABASE_URI)
