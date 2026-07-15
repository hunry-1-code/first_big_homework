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
    """将报告数据渲染为完整 HTML 文档。"""
    title = report.get("title", "")
    overview = report.get("overview_text", "") or ""
    risk = report.get("risk_data", {}) or {}
    trend = report.get("trend_data", {}) or {}
    sentiment = report.get("sentiment_data", {}) or {}
    platforms = report.get("platform_data", {}) or {}
    keywords = report.get("keywords_data", {}) or {}
    opinion = report.get("public_opinion", {}) or {}
    lifecycle = report.get("lifecycle_stage", "")
    heat = report.get("heat_index", 0)
    article_count = report.get("article_count", 0)
    time_code = report.get("time_code", "")
    location = report.get("location", "")
    figures = report.get("key_figures", "")
    cause = report.get("cause", "")

    risk_score = risk.get("score", 0)
    risk_level = risk.get("level", "未知")
    risk_class = "risk-high" if risk_score >= 70 else ("risk-mid" if risk_score >= 40 else "risk-low")
    dates = trend.get("dates", [])
    counts = trend.get("counts", [])
    heat_vals = trend.get("heat", [])

    trend_rows = "".join(
        f"<tr><td>{dates[i] if i < len(dates) else ''}</td>"
        f"<td>{counts[i] if i < len(counts) else ''}</td>"
        f"<td>{heat_vals[i] if i < len(heat_vals) else ''}</td></tr>"
        for i in range(max(len(dates), len(counts)))
    )

    plat_rows = "".join(
        f"<tr><td>{p['platform']}</td><td>{p['count']}</td><td>{round(p.get('percentage',0)*100)}%</td></tr>"
        for p in platforms.get("platforms", [])
    )

    kw_items = keywords.get("keywords", [])[:10]
    kw_rows = "".join(
        f'<span class="tag">{k.get("word","?")}({k.get("weight","-")})</span>'
        for k in kw_items
    )

    cmt_count = opinion.get("comment_count", 0)
    cmt_sent = opinion.get("weighted_sentiment", {})
    cmt_kws = opinion.get("public_keywords", [])[:5]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>事件报告 - {title[:30]}</title>
<style>
  body {{ font-family: "Microsoft YaHei",sans-serif; max-width:860px; margin:0 auto; padding:24px; color:#333; }}
  h1 {{ border-bottom:2px solid #409eff; padding-bottom:10px; font-size:22px; }}
  h2 {{ color:#409eff; margin-top:28px; font-size:17px; }}
  table {{ border-collapse:collapse; width:100%; margin:12px 0; }}
  th,td {{ border:1px solid #ddd; padding:8px; text-align:center; font-size:13px; }}
  th {{ background:#f5f7fa; }}
  .risk {{ padding:8px 16px; border-radius:4px; display:inline-block; color:#fff; font-weight:bold; }}
  .risk-high {{ background:#f56c6c; }}
  .risk-mid {{ background:#e6a23c; }}
  .risk-low {{ background:#67c23a; }}
  .muted {{ color:#909399; font-size:12px; }}
  .tag {{ display:inline-block; background:#ecf5ff; color:#409eff; padding:2px 8px; border-radius:12px; margin:2px; font-size:12px; }}
  .meta {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 16px; font-size:13px; }}
  .meta dt {{ color:#909399; }}
  .meta dd {{ margin:0; font-weight:500; }}
</style>
</head>
<body>
<h1>📊 {title or '事件分析报告'}</h1>
<p class="muted">生成时间：{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} | 报道数：{article_count}篇 | 热度：{heat:.0f} | 生命周期：{lifecycle}</p>

<h2>基本信息</h2>
<dl class="meta">
  <dt>时间</dt><dd>{time_code or '-'}</dd>
  <dt>地点</dt><dd>{location or '-'}</dd>
  <dt>人物/机构</dt><dd>{figures or '-'}</dd>
  <dt>起因</dt><dd>{cause or '-'}</dd>
</dl>

<h2>事件概述</h2>
<p>{overview}</p>

<h2>风险评估</h2>
<p><span class="risk {risk_class}">{risk_level}（{risk_score} 分）</span></p>
<p>可疑报道：{risk.get("suspicious_count", 0)} / {risk.get("total_count", 0)}</p>

<h2>平台分布</h2>
<table>
<tr><th>平台</th><th>报道数</th><th>占比</th></tr>
{plat_rows}
</table>

<h2>发展趋势</h2>
<table>
<tr><th>日期</th><th>报道量</th><th>热度</th></tr>
{trend_rows}
</table>

<h2>情感分析</h2>
<p>正面：{round(float(sentiment.get("positive", 0)) * 100)}% &nbsp;|&nbsp;
负面：{round(float(sentiment.get("negative", 0)) * 100)}% &nbsp;|&nbsp;
中性：{round(float(sentiment.get("neutral", 0)) * 100)}%</p>

<h2>关键词</h2>
<div>{kw_rows}</div>

<h2>公众舆论（{cmt_count}条评论）</h2>
<p>正面：{round(float(cmt_sent.get('positive',0))*100)}% &nbsp;|&nbsp;
负面：{round(float(cmt_sent.get('negative',0))*100)}% &nbsp;|&nbsp;
中性：{round(float(cmt_sent.get('neutral',0))*100)}%</p>
<div>{" ".join(f'<span class="tag">{k["word"]}({k["count"]})</span>' for k in cmt_kws)}</div>

<p class="muted" style="margin-top:32px;">由舆情事件智能分析系统生成</p>
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

    if export_format == "pdf":
        try:
            from weasyprint import HTML
            pdf = HTML(string=html).write_pdf()
            return Response(pdf, mimetype="application/pdf",
                headers={"Content-Disposition": f"attachment; filename=event_report_{event_id}.pdf"})
        except Exception as e:
            from flask import current_app
            current_app.logger.warning("PDF generation failed: %s", e)
            return fail("PDF 生成失败，请尝试 HTML 格式", 500)

    return Response(html, mimetype="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=event_report_{event_id}.html"})

