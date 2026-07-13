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


def _sqlite_allow_heat_without_hotspot(engine) -> None:
    inspector = inspect(engine)
    if "event_heat_snapshot" not in inspector.get_table_names():
        return
    columns = {item["name"]: item for item in inspector.get_columns("event_heat_snapshot")}
    if columns.get("hotspot_run_id", {}).get("nullable"):
        return
    raw_connection = engine.raw_connection()
    cursor = raw_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN")
        cursor.execute(
            """
            CREATE TABLE event_heat_snapshot_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hotspot_run_id INTEGER NULL,
                event_id INTEGER NOT NULL,
                calculated_at DATETIME NOT NULL,
                raw_statistics JSON,
                component_scores JSON,
                core_heat FLOAT NOT NULL,
                spread_heat FLOAT,
                final_heat FLOAT NOT NULL,
                eligible_as_hot BOOLEAN NOT NULL DEFAULT 0,
                rank INTEGER,
                status_change VARCHAR(20),
                time_confidence VARCHAR(20) NOT NULL DEFAULT 'low',
                formula_version VARCHAR(30) NOT NULL DEFAULT 'v1',
                calculation_details JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_event_heat_run_event UNIQUE (hotspot_run_id, event_id),
                FOREIGN KEY(hotspot_run_id) REFERENCES hotspot_run(id) ON DELETE CASCADE,
                FOREIGN KEY(event_id) REFERENCES event(id)
            )
            """
        )
        names = [
            "id",
            "hotspot_run_id",
            "event_id",
            "calculated_at",
            "raw_statistics",
            "component_scores",
            "core_heat",
            "spread_heat",
            "final_heat",
            "eligible_as_hot",
            "rank",
            "status_change",
            "time_confidence",
            "formula_version",
            "calculation_details",
            "created_at",
        ]
        joined = ", ".join(names)
        cursor.execute(
            f"INSERT INTO event_heat_snapshot_new ({joined}) "
            f"SELECT {joined} FROM event_heat_snapshot"
        )
        cursor.execute("DROP TABLE event_heat_snapshot")
        cursor.execute(
            "ALTER TABLE event_heat_snapshot_new RENAME TO event_heat_snapshot"
        )
        cursor.execute(
            "CREATE INDEX ix_event_heat_event_calculated "
            "ON event_heat_snapshot(event_id, calculated_at)"
        )
        cursor.execute(
            "CREATE INDEX ix_event_heat_hot_rank "
            "ON event_heat_snapshot(eligible_as_hot, rank)"
        )
        raw_connection.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        cursor.close()
        raw_connection.close()


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
        _sqlite_allow_heat_without_hotspot(engine)
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
