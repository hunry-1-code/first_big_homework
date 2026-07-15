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


def render_hdbscan_report(
    *,
    analysis_run_id: int,
    aggregation_run_id: int,
    inputs: list[dict],
    assignments: list[dict],
    warnings: list[str],
) -> str:
    noise_count = sum(
        item.get("cluster_index") is None
        or any("HDBSCAN_NOISE" in str(reason) for reason in (item.get("reasons") or []))
        for item in assignments
    )
    lines = [
        "# HDBSCAN 聚合端到端验证报告",
        "",
        f"- 内容分析运行 ID：{analysis_run_id}",
        f"- 聚合运行 ID：{aggregation_run_id}",
        f"- 输入文章数：{len(inputs)}",
        f"- 噪声/延迟分配数：{noise_count}",
        "",
        "## 内容分析输入",
        "",
        "| 文章 ID | 平台 | 标题 | BGE 维度 | TF-IDF 维度 |",
        "|---:|---|---|---:|---:|",
    ]
    for item in inputs:
        lines.append(
            f"| {item['article_id']} | {_cell(item['platform'])} | {_cell(item['title'])} | "
            f"{item['bge_dimension']} | {item['tfidf_dimension']} |"
        )
    lines.extend(
        [
            "",
            "## 簇分配输出",
            "",
            "| 文章 ID | 簇 | 动作 | 判断理由 |",
            "|---:|---:|---|---|",
        ]
    )
    for item in assignments:
        cluster = "噪声/延迟" if item.get("cluster_index") is None else item["cluster_index"]
        lines.append(
            f"| {item['article_id']} | {cluster} | {_cell(item.get('action'))} | {_cell(item.get('reasons') or [])} |"
        )
    lines.extend(["", "## 运行警告与回退", ""])
    if warnings:
        lines.extend(f"- {_cell(item)}" for item in warnings)
    else:
        lines.append("- 无警告；本次使用 HDBSCAN 直接完成聚合。")
    return "\n".join(lines).rstrip() + "\n"


def collect_hdbscan_data(aggregation_run_id: int | None = None):
    from app import create_app
    from app.analysis.event_clusterer import cluster_documents_hdbscan
    from app.models import AggregationRun
    from app.services.event_aggregation_service import _config_from_app, _load_frozen_documents

    app = create_app()
    with app.app_context():
        run = (
            AggregationRun.query.get(aggregation_run_id)
            if aggregation_run_id
            else AggregationRun.query.filter_by(status="success")
            .order_by(AggregationRun.id.desc())
            .first()
        )
        if run is None:
            raise RuntimeError("没有成功的聚合运行可供 HDBSCAN 验证")
        analysis, _rows, _representatives, _articles, documents = _load_frozen_documents(run)
        result = cluster_documents_hdbscan(documents, _config_from_app())
        inputs = [
            {
                "article_id": item.article_id,
                "title": item.title,
                "platform": item.platform,
                "bge_dimension": len(item.bge_vector or []),
                "tfidf_dimension": len(item.tfidf_vector or []),
            }
            for item in documents
        ]
        assignments = [
            {
                "article_id": item.article_id,
                "cluster_index": item.cluster_index,
                "action": item.action,
                "similarity": item.similarity,
                "reasons": item.reasons,
            }
            for item in result.assignments
        ]
        return analysis.id, run.id, inputs, assignments, result.warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aggregation-run-id", type=int)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "docs"
        / "verification"
        / "2026-07-15-hdbscan-pipeline-report.md",
    )
    args = parser.parse_args()
    analysis_id, aggregation_id, inputs, assignments, warnings = collect_hdbscan_data(
        args.aggregation_run_id
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_hdbscan_report(
            analysis_run_id=analysis_id,
            aggregation_run_id=aggregation_id,
            inputs=inputs,
            assignments=assignments,
            warnings=warnings,
        ),
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
