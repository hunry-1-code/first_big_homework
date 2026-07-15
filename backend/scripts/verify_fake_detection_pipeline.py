from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _cell(value) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def render_fake_detection_report(*, event: dict, rows: list[dict]) -> str:
    lines = [
        "# 虚假文本检测端到端验证报告",
        "",
        f"- 事件 ID：{event.get('id')}",
        f"- 事件标题：{event.get('title')}",
        f"- 样本数：{len(rows)}",
        "",
        "> 说明：本模块输出的是可疑风险信号。可疑风险检测不等同于事实核查，也不能单独证明文本为虚假信息。",
        "",
        "## 输入",
        "",
        "| 文章 ID | 平台 | 标题 | 正文节选 |",
        "|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['article_id']} | {_cell(row['platform'])} | {_cell(row['title'])} | {_cell(row['content_excerpt'])} |"
        )
    lines.extend(
        [
            "",
            "## 输出判断",
            "",
            "| 文章 ID | 风险分 | 是否可疑 | 方法 | 原因 | LLM 复核 |",
            "|---:|---:|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['article_id']} | {row['score']} | {'是' if row['is_suspicious'] else '否'} | "
            f"{_cell(row['method'])} | {_cell(row['reason'])} | {_cell(row.get('llm_review') or '未触发/不可用')} |"
        )
    lines.extend(["", "## 特征明细", ""])
    for row in rows:
        lines.extend(
            [
                f"### 文章 {row['article_id']}：{row['title']}",
                "",
                "```json",
                json.dumps(row.get("feature_scores") or {}, ensure_ascii=False, indent=2, sort_keys=True),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def collect_fake_detection_data(event_id: int | None = None, limit: int = 10):
    from app import create_app
    from app.analysis.fake_detector import _build_context, batch_assess_articles
    from app.models import Article, Event

    app = create_app()
    with app.app_context():
        event = Event.query.get(event_id) if event_id else Event.query.order_by(Event.id.desc()).first()
        if event is None:
            raise RuntimeError("没有可用于虚假文本检测的事件")
        articles = (
            Article.query.filter_by(event_id=event.id)
            .order_by(Article.publish_time.asc(), Article.id.asc())
            .limit(max(1, min(int(limit), 50)))
            .all()
        )
        if not articles:
            raise RuntimeError(f"事件 {event.id} 没有文章")
        context = _build_context(event.id, articles)
        results = batch_assess_articles(articles, context)
        rows = []
        for article, result in zip(articles, results):
            evidence = result.get("evidence") or {}
            rows.append(
                {
                    "article_id": article.id,
                    "title": article.title or "",
                    "platform": article.platform or "",
                    "content_excerpt": (article.clean_content or article.raw_content or "")[:240],
                    "score": result.get("score"),
                    "is_suspicious": bool(result.get("is_suspicious")),
                    "method": result.get("method", "rule"),
                    "reason": result.get("reason", ""),
                    "feature_scores": result.get("feature_scores") or {},
                    "llm_review": evidence.get("llm_review"),
                }
            )
        return {"id": event.id, "title": event.title}, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", type=int)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "docs"
        / "verification"
        / "2026-07-15-fake-detection-pipeline-report.md",
    )
    args = parser.parse_args()
    event, rows = collect_fake_detection_data(args.event_id, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_fake_detection_report(event=event, rows=rows), encoding="utf-8"
    )
    print(args.output)


if __name__ == "__main__":
    main()
