from datetime import datetime, timezone

from flask import Blueprint, Response, request

from app.core.response import fail, ok
from app.core.security import login_required
from app.services.report_service import get_report


reports_bp = Blueprint("reports", __name__)


@reports_bp.get("/<int:event_id>/report")
@login_required
def report(event_id: int):
    result = get_report(event_id)
    if result is None:
        return fail("事件不存在", 404)
    return ok(result)


def _build_html_report(report: dict) -> str:
    """将报告数据渲染为 HTML 文档。"""
    event_id = report.get("event_id", "")
    overview = report.get("overview_text", "") or ""
    risk = report.get("risk_data", {}) or {}
    trend = report.get("trend_data", {}) or {}
    sentiment = report.get("sentiment_data", {}) or {}

    risk_score = risk.get("score", 0)
    risk_level = risk.get("level", "未知")
    dates = trend.get("dates", [])
    counts = trend.get("counts", [])
    heat = trend.get("heat", [])

    trend_rows = "".join(
        f"<tr><td>{dates[i] if i < len(dates) else ''}</td>"
        f"<td>{counts[i] if i < len(counts) else ''}</td>"
        f"<td>{heat[i] if i < len(heat) else ''}</td></tr>"
        for i in range(len(dates))
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>事件报告 - {event_id}</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
  h1 {{ border-bottom: 2px solid #409eff; padding-bottom: 10px; }}
  h2 {{ color: #409eff; margin-top: 24px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
  th {{ background: #f5f7fa; }}
  .risk {{ padding: 8px 16px; border-radius: 4px; display: inline-block; color: #fff; }}
  .risk-high {{ background: #f56c6c; }}
  .risk-mid {{ background: #e6a23c; }}
  .risk-low {{ background: #67c23a; }}
  .muted {{ color: #909399; font-size: 13px; }}
</style>
</head>
<body>
<h1>事件分析报告</h1>
<p class="muted">生成时间：{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>

<h2>事件概述</h2>
<p>{overview}</p>

<h2>风险评估</h2>
<p><span class="risk risk-{{"high" if risk_score >= 70 else "mid" if risk_score >= 40 else "low"}}">{risk_level}（{risk_score} 分）</span></p>
<p>可疑报道：{risk.get("suspicious_count", 0)} / {risk.get("total_count", 0)}</p>

<h2>发展趋势</h2>
<table>
<tr><th>日期</th><th>报道量</th><th>热度指数</th></tr>
{trend_rows}
</table>

<h2>情感分析</h2>
<p>正面：{round(float(sentiment.get("positive", 0)) * 100)}% &nbsp;
负面：{round(float(sentiment.get("negative", 0)) * 100)}% &nbsp;
中性：{round(float(sentiment.get("neutral", 0)) * 100)}%</p>

<p class="muted">由舆情事件智能分析系统生成</p>
</body>
</html>"""


@reports_bp.get("/<int:event_id>/report/export")
@login_required
def export_report(event_id: int):
    export_format = request.args.get("format", "html")
    if export_format not in {"html", "pdf"}:
        return fail("format 仅支持 html 或 pdf", 400)
    report = get_report(event_id)
    if report is None:
        return fail("事件不存在", 404)
    html = _build_html_report(report)
    return Response(
        html,
        mimetype="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=event_report_{event_id}.html",
        },
    )

