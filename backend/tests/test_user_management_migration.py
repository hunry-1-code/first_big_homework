import sys, tempfile, unittest
from pathlib import Path
from sqlalchemy import create_engine, text, inspect

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from migrations.migrate_user_management import run_migration

class MigrationTest(unittest.TestCase):
    def test_adds_status_idempotently(self):
        with tempfile.TemporaryDirectory() as d:
            url=f"sqlite:///{Path(d)/'x.db'}"; engine=create_engine(url)
            with engine.begin() as c:
                c.execute(text('CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR(50))'))
                c.execute(text("INSERT INTO user (id,username) VALUES (1,'a')"))
            run_migration(url); run_migration(url)
            self.assertIn('status',{c['name'] for c in inspect(engine).get_columns('user')})
            with engine.connect() as c: self.assertEqual(c.execute(text('SELECT status FROM user')).scalar(),1)
            engine.dispose()
