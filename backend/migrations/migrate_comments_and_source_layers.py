"""Idempotent migration for independent comments and article source layers."""
import os
from sqlalchemy import create_engine, inspect, text

def migrate(database_url: str | None = None) -> None:
    engine = create_engine(database_url or os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        inspector = inspect(conn)
        columns = {c["name"] for c in inspector.get_columns("article")}
        if "source_layer" not in columns:
            conn.execute(text("ALTER TABLE article ADD COLUMN source_layer VARCHAR(24) NOT NULL DEFAULT 'unknown'"))
        if "source_role" not in columns:
            conn.execute(text("ALTER TABLE article ADD COLUMN source_role VARCHAR(32) NOT NULL DEFAULT 'unknown'"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS comment (
          id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL, parent_comment_id INTEGER,
          platform VARCHAR(50) NOT NULL, source_comment_id VARCHAR(255) NOT NULL,
          content TEXT NOT NULL, content_hash VARCHAR(64) NOT NULL,
          content_kind VARCHAR(20) NOT NULL DEFAULT 'comment', author VARCHAR(255),
          likes_count BIGINT DEFAULT 0, replies_count BIGINT DEFAULT 0,
          sentiment_label VARCHAR(20), sentiment_score FLOAT,
          analysis_status VARCHAR(20) DEFAULT 'pending', raw_json JSON,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT uq_comment_platform_source_id UNIQUE(platform, source_comment_id),
          FOREIGN KEY(article_id) REFERENCES article(id), FOREIGN KEY(parent_comment_id) REFERENCES comment(id)
        )"""))
        for statement in (
            "CREATE INDEX IF NOT EXISTS ix_comment_article_id ON comment(article_id)",
            "CREATE INDEX IF NOT EXISTS ix_comment_parent_comment_id ON comment(parent_comment_id)",
            "CREATE INDEX IF NOT EXISTS ix_comment_analysis_status ON comment(analysis_status)",
        ):
            try:
                conn.execute(text(statement))
            except Exception:
                pass
        conn.execute(text("UPDATE article SET source_layer='public', source_role='social_post' WHERE platform IN ('weibo','zhihu','douyin','bilibili','xiaohongshu') AND source_layer='unknown'"))
        conn.execute(text("UPDATE article SET source_layer='institutional', source_role='news_report' WHERE source_layer='unknown'"))

if __name__ == "__main__":
    migrate()
