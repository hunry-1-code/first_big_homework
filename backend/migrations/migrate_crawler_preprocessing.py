from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Config
from app.preprocessing.normalizer import normalize_url


MARKER = "-- PYTHON_URL_HASH_BACKFILL"
SQL_PATH = Path(__file__).with_name("20260710_crawler_preprocessing.sql")


def canonical_url_hash(url: str) -> tuple[str, str]:
    canonical_url = normalize_url(url)
    if canonical_url is None:
        raise ValueError(f"cannot normalize existing article URL: {url!r}")
    return canonical_url, hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()


def _statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def build_url_backfill_plan(rows) -> list[dict[str, object]]:
    plan = []
    owners: dict[str, int] = {}
    duplicates = []
    for row in rows:
        canonical_url, url_hash = canonical_url_hash(row["url"])
        owner_id = owners.get(url_hash)
        if owner_id is not None:
            duplicates.append((owner_id, row["id"], canonical_url))
            continue
        owners[url_hash] = row["id"]
        plan.append(
            {"id": row["id"], "url": canonical_url, "url_hash": url_hash}
        )
    if duplicates:
        details = ", ".join(
            f"{owner_id}/{duplicate_id}: {url}"
            for owner_id, duplicate_id, url in duplicates
        )
        raise RuntimeError(
            "duplicate normalized URLs found; merge or remove these legacy rows before migration: "
            + details
        )
    return plan


def preflight_url_backfill(connection) -> list[dict[str, object]]:
    rows = connection.execute(
        text("SELECT id, url FROM article ORDER BY id")
    ).mappings().all()
    return build_url_backfill_plan(rows)


def execute_statements(connection, statements: list[str]) -> None:
    for statement in statements:
        connection.execute(text(statement))


def run_migration(database_url: str) -> None:
    if not database_url.startswith("mysql"):
        raise RuntimeError("This migration only targets the original MySQL 8 schema.")

    before_backfill, after_backfill = SQL_PATH.read_text(encoding="utf-8").split(MARKER, 1)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        plan = preflight_url_backfill(connection)
        execute_statements(connection, _statements(before_backfill))
        for row in plan:
            connection.execute(
                text("UPDATE article SET url = :url, url_hash = :url_hash WHERE id = :id"),
                row,
            )
        execute_statements(connection, _statements(after_backfill))


if __name__ == "__main__":
    run_migration(Config.SQLALCHEMY_DATABASE_URI)
