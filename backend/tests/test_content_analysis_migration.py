import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app import create_app
from app.extensions import db
from app.models import AnalysisRun, AnalysisRunArticle, ArticleEmbedding
from migrations.migrate_content_analysis import _statements, run_migration


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_ORIGINS = ["http://localhost:5173"]


class ContentAnalysisMigrationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_create_all_registers_analysis_tables(self):
        tables = set(inspect(db.engine).get_table_names())

        self.assertIn("analysis_run", tables)
        self.assertIn("analysis_run_article", tables)
        self.assertIn("article_embedding", tables)

    def test_mysql_schema_contains_json_foreign_keys_and_unique_constraints(self):
        run_sql = str(CreateTable(AnalysisRun.__table__).compile(dialect=mysql.dialect()))
        article_sql = str(
            CreateTable(AnalysisRunArticle.__table__).compile(dialect=mysql.dialect())
        )
        embedding_sql = str(
            CreateTable(ArticleEmbedding.__table__).compile(dialect=mysql.dialect())
        )

        self.assertIn("JSON", run_sql)
        self.assertIn("FOREIGN KEY(user_id)", run_sql)
        self.assertIn("UNIQUE (analysis_run_id, article_id)", article_sql)
        self.assertIn("FOREIGN KEY(article_snapshot_id)", article_sql)
        self.assertIn("JSON", embedding_sql)
        self.assertIn("UNIQUE (article_id, content_identity, model_name, model_version", embedding_sql)

    def test_sql_statement_splitter_ignores_comments(self):
        sql = "-- comment\nCREATE TABLE a (id INT);\n-- second\nCREATE TABLE b (id INT);"

        statements = _statements(sql)

        self.assertEqual(len(statements), 2)
        self.assertTrue(statements[0].startswith("CREATE TABLE a"))

    def test_migration_rejects_non_mysql_database(self):
        with self.assertRaises(RuntimeError):
            run_migration("sqlite:///:memory:")


if __name__ == "__main__":
    unittest.main()
