from __future__ import annotations

import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Config


SQL_PATH = Path(__file__).with_name("20260711_hotspot_discovery.sql")


def _statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def _event_column(statement: str) -> str | None:
    match = re.match(
        r"ALTER\s+TABLE\s+event\s+ADD\s+COLUMN\s+([A-Za-z0-9_]+)",
        statement,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def _constraint_name(statement: str) -> str | None:
    match = re.match(
        r"ALTER\s+TABLE\s+event\s+ADD\s+CONSTRAINT\s+([A-Za-z0-9_]+)",
        statement,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def run_migration(database_url: str) -> None:
    if not database_url.startswith("mysql"):
        raise RuntimeError("This migration only targets MySQL 8.")
    engine = create_engine(database_url)
    statements = _statements(SQL_PATH.read_text(encoding="utf-8"))
    with engine.begin() as connection:
        event_columns = {
            item["name"] for item in inspect(connection).get_columns("event")
        }
        event_constraints = {
            item.get("name")
            for item in inspect(connection).get_foreign_keys("event")
            if item.get("name")
        }
        for statement in statements:
            column = _event_column(statement)
            if column and column in event_columns:
                continue
            constraint = _constraint_name(statement)
            if constraint and constraint in event_constraints:
                continue
            connection.execute(text(statement))
            if column:
                event_columns.add(column)
            if constraint:
                event_constraints.add(constraint)


if __name__ == "__main__":
    run_migration(Config.SQLALCHEMY_DATABASE_URI)
