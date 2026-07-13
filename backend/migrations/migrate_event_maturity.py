from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Config


SQL_PATH = Path(__file__).with_name("20260713_event_maturity.sql")

SQLITE_COLUMNS = {
    "lifecycle_status": "VARCHAR(24) NOT NULL DEFAULT 'data_insufficient'",
    "lifecycle_confidence": "FLOAT NOT NULL DEFAULT 0",
    "lifecycle_evidence": "JSON",
    "lifecycle_updated_at": "DATETIME",
    "metadata_status": "VARCHAR(24) NOT NULL DEFAULT 'pending'",
    "metadata_version": "VARCHAR(32)",
    "metadata_confidence": "FLOAT NOT NULL DEFAULT 0",
    "metadata_evidence": "JSON",
    "metadata_updated_at": "DATETIME",
}


def _statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    return [item.strip() for item in "\n".join(lines).split(";") if item.strip()]


def migrate(database_url: str, *, sql_path: Path = SQL_PATH) -> None:
    engine = create_engine(database_url)
    if engine.dialect.name == "sqlite":
        existing = {item["name"] for item in inspect(engine).get_columns("event")}
        with engine.begin() as connection:
            for name, definition in SQLITE_COLUMNS.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE event ADD COLUMN {name} {definition}")
                    )
            connection.execute(
                text(
                    "UPDATE event SET "
                    "lifecycle_status = COALESCE(lifecycle_status, 'data_insufficient'), "
                    "lifecycle_confidence = COALESCE(lifecycle_confidence, 0), "
                    "metadata_status = COALESCE(metadata_status, 'pending'), "
                    "metadata_confidence = COALESCE(metadata_confidence, 0)"
                )
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
