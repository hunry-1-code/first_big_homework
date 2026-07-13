import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import Event, EventHeatSnapshot
from migrations.migrate_event_maturity import migrate


class EventMaturityMigrationTest(unittest.TestCase):
    def test_event_model_exposes_metadata_maturity_fields(self):
        for name in (
            "metadata_status",
            "metadata_version",
            "metadata_confidence",
            "metadata_evidence",
            "metadata_updated_at",
        ):
            self.assertTrue(hasattr(Event, name), name)

    def test_sql_file_contains_metadata_columns(self):
        sql = (BACKEND_ROOT / "migrations" / "20260713_event_maturity.sql").read_text(
            encoding="utf-8"
        )
        for name in (
            "metadata_status",
            "metadata_version",
            "metadata_confidence",
            "metadata_evidence",
            "metadata_updated_at",
        ):
            self.assertIn(name, sql)
        self.assertIn("MODIFY COLUMN hotspot_run_id BIGINT NULL", sql)

    def test_heat_snapshot_allows_non_hotspot_sources(self):
        self.assertTrue(EventHeatSnapshot.__table__.c.hotspot_run_id.nullable)

    def test_runner_upgrades_existing_sqlite_event_table(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy.db"
            database_url = f"sqlite:///{database_path.as_posix()}"
            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE event ("
                        "id INTEGER PRIMARY KEY, title VARCHAR(255) NOT NULL"
                        ")"
                    )
                )
            engine.dispose()

            migrate(database_url)

            upgraded = create_engine(database_url)
            columns = {item["name"] for item in inspect(upgraded).get_columns("event")}
            upgraded.dispose()
            self.assertTrue(
                {
                    "lifecycle_status",
                    "lifecycle_confidence",
                    "lifecycle_evidence",
                    "lifecycle_updated_at",
                    "metadata_status",
                    "metadata_version",
                    "metadata_confidence",
                    "metadata_evidence",
                    "metadata_updated_at",
                }.issubset(columns)
            )

    def test_runner_makes_existing_sqlite_heat_source_nullable(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy-heat.db"
            database_url = f"sqlite:///{database_path.as_posix()}"
            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE event ("
                        "id INTEGER PRIMARY KEY, title VARCHAR(255) NOT NULL"
                        ")"
                    )
                )
                connection.execute(
                    text(
                        "CREATE TABLE hotspot_run (id INTEGER PRIMARY KEY)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE TABLE event_heat_snapshot ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "hotspot_run_id INTEGER NOT NULL, event_id INTEGER NOT NULL, "
                        "calculated_at DATETIME NOT NULL, raw_statistics JSON, "
                        "component_scores JSON, core_heat FLOAT NOT NULL, "
                        "spread_heat FLOAT, final_heat FLOAT NOT NULL, "
                        "eligible_as_hot BOOLEAN NOT NULL DEFAULT 0, rank INTEGER, "
                        "status_change VARCHAR(20), time_confidence VARCHAR(20) NOT NULL DEFAULT 'low', "
                        "formula_version VARCHAR(30) NOT NULL DEFAULT 'v1', "
                        "calculation_details JSON, created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                        ")"
                    )
                )
            engine.dispose()

            migrate(database_url)

            upgraded = create_engine(database_url)
            columns = {
                item["name"]: item
                for item in inspect(upgraded).get_columns("event_heat_snapshot")
            }
            upgraded.dispose()
            self.assertTrue(columns["hotspot_run_id"]["nullable"])


if __name__ == "__main__":
    unittest.main()
