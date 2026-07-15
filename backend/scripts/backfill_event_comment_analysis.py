from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.models import Article, Comment
from app.services.event_comment_analysis_service import analyze_event_comments


def select_event_ids() -> list[int]:
    rows = (
        Article.query.with_entities(Article.event_id)
        .join(Comment, Comment.article_id == Article.id)
        .filter(Article.event_id.isnot(None))
        .distinct()
        .order_by(Article.event_id)
        .all()
    )
    return [int(row[0]) for row in rows]


def run_backfill(event_ids: list[int], *, dry_run: bool) -> dict:
    summary = {
        "selected_event_ids": [int(event_id) for event_id in event_ids],
        "processed": 0,
        "failed": 0,
        "results": [],
    }
    if dry_run:
        return summary
    for event_id in event_ids:
        try:
            result = analyze_event_comments(int(event_id))
            summary["processed"] += 1
            summary["results"].append(
                {"event_id": int(event_id), "sentiment": result.get("sentiment", {})}
            )
        except Exception as exc:
            summary["failed"] += 1
            summary["results"].append(
                {"event_id": int(event_id), "error": type(exc).__name__}
            )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="补跑正式事件的评论分析")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--event-id", type=int)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        event_ids = select_event_ids() if args.all else [args.event_id]
        print(json.dumps(run_backfill(event_ids, dry_run=args.dry_run), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
