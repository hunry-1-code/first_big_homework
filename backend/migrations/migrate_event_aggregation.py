from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Config


SQL_PATH = Path(__file__).with_name("20260711_event_aggregation.sql")


def _statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    return [item.strip() for item in "\n".join(lines).split(";") if item.strip()]


def run_migration(database_url: str) -> None:
    if not database_url.startswith("mysql"):
        raise RuntimeError("This migration only targets MySQL 8.")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        for statement in _statements(SQL_PATH.read_text(encoding="utf-8")):
            connection.execute(text(statement))


if __name__ == "__main__":
    run_migration(Config.SQLALCHEMY_DATABASE_URI)
