import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class MigrationTest(unittest.TestCase):
    def test_url_hash_backfill_uses_runtime_url_normalization(self):
        migration_path = BACKEND_ROOT / "migrations" / "migrate_crawler_preprocessing.py"
        self.assertTrue(migration_path.exists())
        spec = importlib.util.spec_from_file_location("crawler_migration", migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        canonical_url, url_hash = module.canonical_url_hash(
            "HTTPS://Example.COM:443/news/1?utm_source=test&b=2#section"
        )

        self.assertEqual(canonical_url, "https://example.com/news/1?b=2")
        self.assertEqual(len(url_hash), 64)

    def test_sql_migration_does_not_hash_raw_urls(self):
        sql = (BACKEND_ROOT / "migrations" / "20260710_crawler_preprocessing.sql").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("SHA2(url, 256)", sql)
        self.assertIn("-- PYTHON_URL_HASH_BACKFILL", sql)
        self.assertIn("heartbeat_at", sql)
        self.assertIn("lease_token", sql)
        self.assertIn("attempt", sql)

    def test_duplicate_normalized_urls_abort_before_schema_changes(self):
        migration_path = BACKEND_ROOT / "migrations" / "migrate_crawler_preprocessing.py"
        spec = importlib.util.spec_from_file_location("crawler_migration_duplicates", migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertTrue(hasattr(module, "build_url_backfill_plan"))
        with self.assertRaisesRegex(RuntimeError, "duplicate normalized URLs"):
            module.build_url_backfill_plan(
                [
                    {"id": 1, "url": "https://example.com/news/1?utm_source=a"},
                    {"id": 2, "url": "https://example.com/news/1?utm_source=b"},
                ]
            )

    def test_migration_preflights_urls_before_running_ddl(self):
        migration_path = BACKEND_ROOT / "migrations" / "migrate_crawler_preprocessing.py"
        spec = importlib.util.spec_from_file_location("crawler_migration_order", migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        order = []

        self.assertTrue(hasattr(module, "preflight_url_backfill"))
        self.assertTrue(hasattr(module, "execute_statements"))

        class FakeTransaction:
            def __enter__(self):
                return object()

            def __exit__(self, exc_type, exc, traceback):
                return False

        class FakeEngine:
            def begin(self):
                return FakeTransaction()

        with patch.object(module, "create_engine", return_value=FakeEngine()), patch.object(
            module,
            "preflight_url_backfill",
            side_effect=lambda connection: order.append("preflight") or [],
        ), patch.object(
            module,
            "execute_statements",
            side_effect=lambda connection, statements: order.append("ddl"),
        ):
            module.run_migration("mysql+pymysql://example")

        self.assertEqual(order[0], "preflight")


if __name__ == "__main__":
    unittest.main()
