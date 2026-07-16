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
    """将报告数据渲染为完整 HTML 文档，包含详细报告页面的所有内容。"""
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
    articles = report.get("articles", [])
    prediction = report.get("prediction", {}) or {}
    propagation = report.get("propagation") or {}
    sent_pos = report.get("sentiment_positive", 0)
    sent_neg = report.get("sentiment_negative", 0)
    sent_neu = report.get("sentiment_neutral", 0)

    risk_score = risk.get("score", 0)
    risk_level = risk.get("level", "未知")
    risk_class = "risk-high" if risk_score >= 70 else ("risk-mid" if risk_score >= 40 else "risk-low")
    risk_factors = risk.get("factors", [])
    dates = trend.get("dates", [])
    counts = trend.get("counts", [])
    heat_vals = trend.get("heat", [])
    key_points = trend.get("key_points", [])

    # ---------- 辅助函数 ----------
    def _pct(v):
        """将小数转为百分比字符串"""
        try:
            return f"{round(float(v) * 100)}%"
        except (TypeError, ValueError):
            return "-"

    def _esc(text):
        """简单转义 HTML 特殊字符"""
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ---------- 发展趋势表格 ----------
    trend_rows = "".join(
        f"<tr><td>{dates[i] if i < len(dates) else ''}</td>"
        f"<td>{counts[i] if i < len(counts) else ''}</td>"
        f"<td>{heat_vals[i] if i < len(heat_vals) else ''}</td></tr>"
        for i in range(max(len(dates), len(counts)))
    )

    # ---------- 关键节点 ----------
    key_points_html = ""
    if key_points:
        kp_items = "".join(
            f"<li>{_esc(p.get('name', '?'))} — {_esc(str(p.get('coord', '')))}</li>"
            for p in key_points
        )
        key_points_html = f"<h3>📌 关键节点</h3><ul>{kp_items}</ul>"

    # ---------- 平台分布 ----------
    plat_rows = "".join(
        f"<tr><td>{_esc(p.get('platform','?'))}</td><td>{p.get('count',0)}</td><td>{round(p.get('percentage',0)*100)}%</td></tr>"
        for p in platforms.get("platforms", [])
    )

    # ---------- 关键词 ----------
    kw_items = keywords.get("keywords", [])[:15]
    kw_rows = "".join(
        f'<span class="tag">{_esc(str(k.get("word","?")))}({k.get("weight","-")})</span>'
        for k in kw_items
    )

    # ---------- 风险因素 ----------
    risk_factors_html = ""
    if risk_factors:
        rf_items = "".join(f"<li>{_esc(f)}</li>" for f in risk_factors)
        risk_factors_html = f"<h3>⚠️ 风险因素</h3><ul>{rf_items}</ul>"

    # ---------- 预测 ----------
    prediction_html = ""
    if prediction:
        pred_parts = []
        conf = prediction.get("confidence")
        if conf is not None:
            pred_parts.append(f"置信度：{round(float(conf) * 100)}%")
        td = prediction.get("trend_direction")
        if td:
            pred_parts.append(f"趋势方向：{_esc(str(td))}")
        ns = prediction.get("next_stage")
        if ns:
            pred_parts.append(f"预测下一阶段：{_esc(str(ns))}")
        if pred_parts:
            prediction_html = (
                '<div class="info-box">'
                + " &nbsp;|&nbsp; ".join(pred_parts)
                + "</div>"
            )

    # ---------- 公众舆论 ----------
    cmt_count = opinion.get("comment_count", 0)
    cmt_sent = opinion.get("weighted_sentiment", {})
    cmt_kws = opinion.get("public_keywords", [])
    official_kws = opinion.get("official_keywords", [])
    public_demands = opinion.get("public_demands", [])
    opinion_themes = opinion.get("opinion_themes") or []
    narrative_gap = opinion.get("narrative_gap_analysis") or {}
    gap_interpretation = opinion.get("gap_interpretation", "")
    opinion_divergence = opinion.get("opinion_divergence")
    negative_rate = opinion.get("negative_rate")
    sentiment_corrected = opinion.get("sentiment_corrected_count", 0)
    coverage_warning = opinion.get("coverage_warning", "")
    analysis_mode = opinion.get("analysis_mode", "")

    # 公众舆论 HTML
    opinion_parts = []

    if cmt_count > 0:
        opinion_parts.append(f"""<div class="opinion-stats">
  <div class="stat-card"><div class="stat-label">评论样本</div><div class="stat-value">{cmt_count}</div><div class="stat-sub">条公众评论</div></div>
  <div class="stat-card"><div class="stat-label">公众负面率</div><div class="stat-value" style="color:#f56c6c">{_pct(negative_rate)}</div><div class="stat-sub">情感校正 {sentiment_corrected} 条</div></div>
  <div class="stat-card"><div class="stat-label">意见分歧度</div><div class="stat-value" style="color:#e6a23c">{_pct(opinion_divergence)}</div><div class="stat-sub">观点一致性指标</div></div>
  <div class="stat-card"><div class="stat-label">加权情感分布</div><div class="stat-value" style="font-size:13px">
    正面 {_pct(cmt_sent.get('positive',0))} &nbsp;|&nbsp;
    负面 {_pct(cmt_sent.get('negative',0))} &nbsp;|&nbsp;
    中性 {_pct(cmt_sent.get('neutral',0))}
  </div><div class="stat-sub">长度+点赞质量加权</div></div>
</div>""")

    # AI 主题
    if opinion_themes:
        themes_by_sent = {"positive": [], "negative": [], "neutral": []}
        for t in opinion_themes:
            s = t.get("sentiment", "neutral")
            if s not in themes_by_sent:
                s = "neutral"
            themes_by_sent[s].append(t)
        theme_html = ""
        for sent_label, icon, color in [("positive", "😊 正面", "#67c23a"), ("negative", "😡 负面", "#f56c6c"), ("neutral", "😐 中性", "#909399")]:
            items = themes_by_sent.get(sent_label, [])
            if not items:
                continue
            tags = " ".join(
                f'<span class="opinion-tag" style="background:{color}15;color:{color};border:1px solid {color}40">{_esc(t.get("theme","?"))} <small>{_esc(str(t.get("example",""))[:20])}</small></span>'
                for t in items
            )
            theme_html += f"<div style='margin-bottom:6px'><strong style='color:{color}'>{icon}</strong> {tags}</div>"
        if theme_html:
            opinion_parts.append(f"<h3>🤖 AI 识别公众关注主题</h3>{theme_html}")

    # 叙事差异
    if narrative_gap:
        gap_html = f"""<h3>📰 媒体与公众叙事差异</h3>
<div class="info-box">
  <p><strong>媒体强调：</strong>{_esc(narrative_gap.get('media_focus','-'))}</p>
  <p><strong>公众关注：</strong>{_esc(narrative_gap.get('public_focus','-'))}</p>
  <p><strong>核心差异：</strong>{_esc(narrative_gap.get('gap','-'))}</p>
  <p>差异强度：<span class="tag" style="background:{'#f56c6c' if narrative_gap.get('intensity')=='high' else '#e6a23c'};color:#fff">{_esc(narrative_gap.get('intensity','-'))}</span></p>
</div>"""
        opinion_parts.append(gap_html)

    # 关键词 + 诉求三列
    off_kw = " ".join(f'<span class="tag">{_esc(k.get("word","?"))}({k.get("count",0)})</span>' for k in official_kws) if official_kws else '<span class="muted">暂无机构数据</span>'
    pub_kw = " ".join(f'<span class="tag tag-red">{_esc(k.get("word","?"))}({k.get("count",0)})</span>' for k in cmt_kws) if cmt_kws else '<span class="muted">暂无评论数据</span>'
    demands = "".join(f"<tr><td>{_esc(d.get('demand','?'))}</td><td><strong>{d.get('count',0)}</strong></td></tr>" for d in public_demands) if public_demands else "<tr><td colspan='2' class='muted'>暂未识别出明确诉求</td></tr>"

    opinion_parts.append(f"""<h3>📋 关键词与诉求对比</h3>
<table><tr><th style="width:33%">机构侧关键词</th><th style="width:33%">公众高频表达</th><th style="width:34%">公众诉求</th></tr>
<tr><td style="vertical-align:top">{off_kw}</td><td style="vertical-align:top">{pub_kw}</td><td style="vertical-align:top"><table class="inner-table">{demands}</table></td></tr></table>""")

    # 核心判断
    if gap_interpretation:
        opinion_parts.append(f"<p><strong>💡 核心判断：</strong>{_esc(gap_interpretation)}；公众意见分歧度 {_pct(opinion_divergence)}</p>")

    # 覆盖警告
    if coverage_warning:
        opinion_parts.append(f'<div class="warning-box">{_esc(str(coverage_warning))}</div>')

    public_opinion_html = "".join(opinion_parts) if opinion_parts else "<p class='muted'>暂无公众舆论数据</p>"

    # ---------- 事件溯源与传播路径 ----------
    propagation_html = ""
    if propagation:
        prop_parts = []
        origin = (propagation.get("origin_analysis") or {}).get("origin")
        if origin:
            prop_parts.append(f"""<h3>🔍 疑似最早公开来源</h3>
<div class="info-box" style="border-left-color:#409eff">
  <p><strong>置信度：{round(float(origin.get('confidence',0))*100)}%</strong></p>
  <p><strong>标题：</strong>{_esc(origin.get('title','-'))}</p>
  <p><strong>来源：</strong>{_esc(origin.get('source','-'))}</p>
</div>""")

        nodes = (propagation.get("graph") or {}).get("nodes", [])
        links = (propagation.get("graph") or {}).get("links", [])
        if nodes:
            node_colors = ["#dc2626", "#ea580c", "#2563eb", "#16a34a", "#9333ea", "#db2777"]
            node_bgs = ["#fee2e2", "#ffedd5", "#dbeafe", "#dcfce7", "#f3e8ff", "#fce7f3"]
            node_spans = " → ".join(
                f'<span class="prop-node" style="background:{node_bgs[i%6]};color:{node_colors[i%6]}">{_esc(n.get("name","?"))}</span>'
                for i, n in enumerate(nodes)
            )
            prop_parts.append(f"<h3>📡 关键词传播演化链</h3><p style='line-height:2.5'>{node_spans}</p>")

            # 关键词解释
            explanations = (propagation.get("llm_analysis") or {}).get("keyword_explanations", [])
            kw_expls = [e for e in explanations if e and e.get("type") == "keyword"]
            if kw_expls:
                expl_rows = "".join(
                    f"<tr><td style='color:{node_colors[i%6]};font-weight:bold'>{_esc(e.get('target','?'))}</td><td>{_esc(e.get('reason','-'))}</td></tr>"
                    for i, e in enumerate(kw_expls)
                )
                prop_parts.append(f"<h3>📖 关键词含义与演化推导</h3><table><tr><th>关键词</th><th>含义解释</th></tr>{expl_rows}</table>")

        summary_notice = (propagation.get("summary") or {}).get("coverage_notice", "")
        if summary_notice:
            prop_parts.append(f'<p class="muted">{_esc(summary_notice)}</p>')

        propagation_html = "".join(prop_parts) if prop_parts else ""

    if not propagation_html:
        propagation_html = "<p class='muted'>暂无传播路径数据</p>"

    # ---------- 报道影响力排行 ----------
    influence_html = ""
    if articles:
        with_interactions = [a for a in articles if (a.get("reposts_count", 0) or 0) + (a.get("comments_count", 0) or 0) + (a.get("likes_count", 0) or 0) > 0]
        if with_interactions:
            sorted_articles = sorted(
                with_interactions,
                key=lambda a: (a.get("reposts_count", 0) or 0) * 1.0 + (a.get("comments_count", 0) or 0) * 0.8 + (a.get("likes_count", 0) or 0) * 0.3,
                reverse=True,
            )[:20]
            inf_rows = "".join(
                f"<tr><td>{i+1}</td><td>{_esc(a.get('title','-')[:60])}</td><td>{_esc(a.get('platform','-'))}</td>"
                f"<td>↺{a.get('reposts_count',0)} 💬{a.get('comments_count',0)} ♥{a.get('likes_count',0)}</td></tr>"
                for i, a in enumerate(sorted_articles)
            )
            influence_html = f"<h2>📊 报道传播影响力排行</h2><table><tr><th>#</th><th>标题</th><th>平台</th><th>互动量</th></tr>{inf_rows}</table>"

    # ---------- 关联报道列表 ----------
    articles_html = ""
    if articles:
        def _render_article_kws(article_keywords):
            """渲染单篇文章的关键词标签"""
            parts = []
            for kw in (article_keywords or [])[:5]:
                word = _esc(str(kw.get("word", "?")))
                parts.append(f'<span class="tag tag-sm">{word}</span>')
            return " ".join(parts)

        art_parts = []
        for i, a in enumerate(articles[:100]):
            kws_html = _render_article_kws(a.get("keywords"))
            art_parts.append(
                f"<tr><td>{i+1}</td><td>{_esc(a.get('title','-')[:80])}</td>"
                f"<td>{_esc(a.get('platform','-'))}</td>"
                f"<td>{_esc(str(a.get('author','-')))}</td>"
                f"<td>{_esc(str(a.get('publish_time','-'))[:10])}</td>"
                f"<td>{_esc(str(a.get('sentiment_label','-')))}</td>"
                f"<td>{'⚠️可疑' if a.get('is_suspicious') else '✔️真实'}</td>"
                f"<td>{kws_html}</td></tr>"
            )
        art_rows = "".join(art_parts)
        articles_html = f"""<h2>📰 关联舆情报道列表（共 {len(articles)} 篇，显示前 100 篇）</h2>
<table class='articles-table'>
<tr><th>#</th><th>标题</th><th>平台</th><th>作者</th><th>时间</th><th>情感</th><th>真实性</th><th>关键词</th></tr>
{art_rows}
</table>"""

    # ---------- 组装完整 HTML ----------
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>事件报告 - {title[:30]}</title>
<style>
  body {{ font-family: "Microsoft YaHei","PingFang SC",sans-serif; max-width:960px; margin:0 auto; padding:24px; color:#333; line-height:1.6; }}
  h1 {{ border-bottom:2px solid #409eff; padding-bottom:10px; font-size:22px; }}
  h2 {{ color:#409eff; margin-top:28px; font-size:17px; border-left:3px solid #409eff; padding-left:10px; }}
  h3 {{ font-size:14px; color:#606266; margin-top:18px; margin-bottom:8px; }}
  table {{ border-collapse:collapse; width:100%; margin:12px 0; }}
  th,td {{ border:1px solid #ddd; padding:8px; text-align:center; font-size:13px; }}
  th {{ background:#f5f7fa; font-weight:600; }}
  .articles-table th,.articles-table td {{ font-size:11px; padding:5px 4px; }}
  .articles-table td {{ text-align:left; }}
  .risk {{ padding:8px 16px; border-radius:4px; display:inline-block; color:#fff; font-weight:bold; }}
  .risk-high {{ background:#f56c6c; }}
  .risk-mid {{ background:#e6a23c; }}
  .risk-low {{ background:#67c23a; }}
  .muted {{ color:#909399; font-size:12px; }}
  .tag {{ display:inline-block; background:#ecf5ff; color:#409eff; padding:2px 8px; border-radius:12px; margin:2px; font-size:12px; }}
  .tag-red {{ background:#fef0f0; color:#f56c6c; }}
  .tag-sm {{ font-size:10px; padding:1px 5px; }}
  .meta {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 16px; font-size:13px; }}
  .meta dt {{ color:#909399; }}
  .meta dd {{ margin:0; font-weight:500; }}
  .info-box {{ background:#f8f9fc; border-left:3px solid #409eff; padding:12px 16px; margin:12px 0; border-radius:0 6px 6px 0; font-size:13px; }}
  .info-box p {{ margin:4px 0; }}
  .warning-box {{ background:#fef8e7; border:1px solid #f5dAB1; padding:10px 14px; margin:12px 0; border-radius:6px; font-size:13px; color:#b88230; }}
  .opinion-stats {{ display:flex; gap:12px; margin:12px 0; flex-wrap:wrap; }}
  .stat-card {{ flex:1; min-width:140px; background:#f8f9fc; border-radius:8px; padding:12px; text-align:center; }}
  .stat-label {{ font-size:12px; color:#909399; margin-bottom:4px; }}
  .stat-value {{ font-size:22px; font-weight:bold; color:#303133; }}
  .stat-sub {{ font-size:11px; color:#c0c4cc; margin-top:2px; }}
  .opinion-tag {{ display:inline-block; padding:2px 10px; border-radius:14px; margin:2px; font-size:12px; }}
  .prop-node {{ display:inline-block; padding:3px 10px; border-radius:6px; margin:0 1px; font-size:13px; font-weight:500; }}
  .inner-table {{ margin:0; }}
  .inner-table th,.inner-table td {{ border:none; padding:4px 6px; font-size:12px; }}
  ul {{ margin:4px 0; padding-left:20px; }}
  li {{ font-size:13px; margin:2px 0; }}
</style>
</head>
<body>
<h1>📊 {title or '事件分析报告'}</h1>
<p class="muted">生成时间：{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
 | 报道数：{article_count}篇 | 热度：{heat:.0f} | 生命周期：{_esc(lifecycle)}
{prediction_html}
</p>

<h2>基本信息</h2>
<dl class="meta">
  <dt>时间</dt><dd>{_esc(time_code) or '-'}</dd>
  <dt>地点</dt><dd>{_esc(location) or '-'}</dd>
  <dt>人物/机构</dt><dd>{_esc(figures) or '-'}</dd>
  <dt>起因</dt><dd>{_esc(cause) or '-'}</dd>
</dl>

<h2>事件概述</h2>
<p>{overview}</p>

<h2>风险评估</h2>
<p><span class="risk {risk_class}">{_esc(risk_level)}（{risk_score} 分）</span></p>
<p>可疑报道：{risk.get("suspicious_count", 0)} / {risk.get("total_count", 0)}</p>
{risk_factors_html}

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
{key_points_html}

<h2>情感分析</h2>
<p>正面：{_pct(sent_pos)} &nbsp;|&nbsp; 负面：{_pct(sent_neg)} &nbsp;|&nbsp; 中性：{_pct(sent_neu)}</p>
<p class="muted">（基于全部报道正文的情感分析结果）</p>

<h2>关键词</h2>
<div>{kw_rows}</div>

<h2>公众舆论（{cmt_count}条评论）</h2>
{public_opinion_html}

<h2>事件溯源与关键传播路径</h2>
{propagation_html}

{influence_html}
{articles_html}

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

