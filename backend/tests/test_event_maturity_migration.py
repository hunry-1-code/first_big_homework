import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import Event
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


if __name__ == "__main__":
    unittest.main()
