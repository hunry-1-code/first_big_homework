"""全链路端到端测试：publish 所有簇 → 完整 API 验证 → 前后端对齐"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from app import create_app
app = create_app()

with app.app_context():
    from app.extensions import db
    from app.models import (
        AggregationCluster, AggregationRun, Event, EventArticleMembership,
        Article, ArticleEmbedding, SentimentRun, ArticleSentimentResult,
        Report, EventSentimentSnapshot
    )
    from app.services.event_aggregation_service import publish_cluster
    from app.services.event_service import get_event_detail, get_propagation_data
    from app.services.sentiment_analysis_service import get_event_sentiment

    # ── 1. Publish 所有多成员簇 ──
    print("=" * 60)
    print("1. Publish clusters")
    # 取最新的 AggregationRun
    agr = AggregationRun.query.order_by(AggregationRun.id.desc()).first()
    print(f"   AggregationRun id={agr.id} scope={agr.scope} status={agr.status}")
    clusters = AggregationCluster.query.filter_by(aggregation_run_id=agr.id)\
        .filter(AggregationCluster.member_count > 1)\
        .order_by(AggregationCluster.member_count.desc()).all()
    print(f"   多成员簇: {len(clusters)} 个")

    published_ids = []
    for c in clusters:
        if c.resolved_event_id:
            print(f"   [{c.cluster_index}] already published -> event_id={c.resolved_event_id}")
            published_ids.append(c.resolved_event_id)
        else:
            try:
                r = publish_cluster(c.id, user_id=1)
                eid = r.get("event_id")
                print(f"   [{c.cluster_index}] members={c.member_count} -> event_id={eid} postprocess={r.get('postprocess',{}).get('sentiment','?')}")
                published_ids.append(eid)
            except Exception as e:
                print(f"   [{c.cluster_index}] FAILED: {e}")

    # ── 2. 全部事件概览 ──
    print("\n" + "=" * 60)
    print("2. Event overview")
    events = Event.query.all()
    print(f"   总事件: {len(events)}")
    for e in events:
        mem = EventArticleMembership.query.filter_by(event_id=e.id, is_active=True).count()
        art_count = Article.query.filter_by(event_id=e.id).count()
        has_report = Report.query.filter_by(event_id=e.id).first() is not None
        has_sentiment = e.sentiment_positive is not None
        print(f"   id={e.id} members={mem} articles={art_count} report={'Y' if has_report else 'N'} sentiment={'Y' if has_sentiment else 'N'}")
        print(f"     title: {e.title[:80] if e.title else 'N/A'}")
        print(f"     heat={e.heat_index} lifecycle={e.lifecycle_stage} hot={e.is_hot}")
        print(f"     sentiment: +{e.sentiment_positive} / -{e.sentiment_negative} / ~{e.sentiment_neutral}")

    # ── 3. 完整 API 验证 ──
    print("\n" + "=" * 60)
    print("3. Full API response validation")
    print("   Frontend field         │ Backend  │ Verdict")
    print("   ───────────────────────┼──────────┼───────")

    all_ok = True
    for e in events:
        detail = get_event_detail(e.id)
        sentiment = get_event_sentiment(e.id)
        prop = get_propagation_data(e.id)

        checks = [
            # Basic
            ("detail.title", detail.get("title"), "str"),
            ("detail.heat_index", detail.get("heat_index"), "num"),
            ("detail.core_heat", detail.get("core_heat"), "num"),
            ("detail.spread_heat", detail.get("spread_heat"), "any"),
            ("detail.is_hot", detail.get("is_hot"), "bool"),
            ("detail.hot_rank", detail.get("hot_rank"), "any"),
            ("detail.lifecycle_stage", detail.get("lifecycle_stage"), "str"),
            ("detail.time_confidence", detail.get("time_confidence"), "str"),
            ("detail.first_publish_time", detail.get("first_publish_time"), "str"),
            ("detail.last_activity_time", detail.get("last_activity_time"), "any"),
            # Sentiment
            ("detail.sentiment_positive", detail.get("sentiment_positive"), "num"),
            ("detail.sentiment_negative", detail.get("sentiment_negative"), "num"),
            ("detail.sentiment_neutral", detail.get("sentiment_neutral"), "num"),
            # Nested - Report
            ("detail.report.overview_text", (detail.get("report") or {}).get("overview_text"), "str"),
            ("detail.report.risk_data", (detail.get("report") or {}).get("risk_data"), "dict"),
            # Nested - Trend
            ("detail.trend.dates", (detail.get("trend") or {}).get("dates"), "list"),
            ("detail.trend.counts", (detail.get("trend") or {}).get("counts"), "list"),
            ("detail.trend.key_points", (detail.get("trend") or {}).get("key_points"), "list"),
            # Nested - Sentiment
            ("sentiment.positive", sentiment.get("positive"), "num"),
            ("sentiment.negative", sentiment.get("negative"), "num"),
            ("sentiment.neutral", sentiment.get("neutral"), "num"),
            ("sentiment.daily_trend (daily)", sentiment.get("daily"), "list"),
            ("sentiment.platform_distribution", sentiment.get("platform_distribution"), "list"),
            # Nested - Platform
            ("detail.platform.platforms", (detail.get("platform") or {}).get("platforms"), "list"),
            # Nested - Keywords
            ("detail.keywords.keywords", (detail.get("keywords") or {}).get("keywords"), "list"),
            # Nested - Articles
            ("detail.articles.articles", (detail.get("articles") or {}).get("articles"), "list"),
            # Propagation
            ("prop.key_nodes", prop.get("key_nodes"), "list"),
            ("prop.graph.nodes", (prop.get("graph") or {}).get("nodes"), "list"),
            ("prop.graph.links", (prop.get("graph") or {}).get("links"), "list"),
        ]

        for label, val, expected in checks:
            ok = False
            if expected == "str":   ok = isinstance(val, str) and len(val) > 0
            elif expected == "num": ok = isinstance(val, (int, float)) and val is not None
            elif expected == "list": ok = isinstance(val, list) and len(val) > 0
            elif expected == "dict": ok = isinstance(val, dict) and len(val) > 0
            elif expected == "bool": ok = isinstance(val, bool)
            elif expected == "any":  ok = val is not None

            extra = ""
            if isinstance(val, list): extra = f"({len(val)})"
            elif isinstance(val, dict): extra = f"({len(val)}k)"
            elif isinstance(val, str) and len(val) > 30: extra = val[:30] + "..."

            status = "OK" if ok else "MISS"
            if not ok: all_ok = False
            print(f"   {label:35s} │ {status:8s} │ {extra}")

    # ── 4. 前端差异对照 ──
    print("\n" + "=" * 60)
    print("4. Frontend detail.vue gap analysis")
    gaps = [
        ("传播图 buildPropagationData()", "硬编码 14 个假节点",
         f"后端 {sum(len((p.get('graph',{}).get('nodes') or [])) for e in events for p in [get_propagation_data(e.id)] if p)} 个真节点",
         "❌ 前端未调用 /propagation API，需替换 buildPropagationData()"),
        ("情感趋势 initSentimentTrendChart()", "sin/cos 模拟曲线",
         f"后端 {sum(len((get_event_sentiment(e.id) or {}).get('daily') or []) for e in events)} 天真数据",
         "❌ 前端未用 sentiment.daily_trend，需替换模拟逻辑"),
        ("词云 initBubbleChart()", "keywords.kw_list 为空时不渲染",
         f"后端 keywords={sum(len((get_event_detail(e.id).get('keywords',{}).get('keywords') or [])) for e in events)} 词",
         "✅ 修复后 keywords 有数据，但需确认前端读取路径"),
        ("AI 元数据栏", "显示「待后端录入」",
         "Event 表缺 time_code/location/key_figures/cause 字段",
         "⚠️ 需后端加字段或前端去掉此栏"),
        ("平台 Badge getPlatformBadges()", "eventId % 3 随机",
         "后端 platform.platforms 有真实分布",
         "❌ 前端硬编码，需改为从 API 读取"),
        ("影响排行 buildInfluenceData()", "手动加随机噪声",
         "后端 articles.articles 有真互动数",
         "❌ 前端截取标题+加随机数，需清理"),
    ]
    for name, frontend, backend, verdict in gaps:
        print(f"\n   🔴 {name}")
        print(f"      前端: {frontend}")
        print(f"      后端: {backend}")
        print(f"      → {verdict}")

    # ── 5. 数据量统计 ──
    print("\n" + "=" * 60)
    print("5. Data quality stats")
    total_articles = Article.query.count()
    cleaned = Article.query.filter(Article.clean_status == "success").count()
    with_sent = Article.query.filter(Article.sentiment_label.isnot(None)).count()
    with_embed = ArticleEmbedding.query.count()
    total_events = Event.query.count()
    total_reports = Report.query.count()
    print(f"   Articles: {total_articles} total, {cleaned} cleaned, {with_sent} sentiment-labelled")
    print(f"   Embeddings: {with_embed}")
    print(f"   Events: {total_events}")
    print(f"   Reports: {total_reports}")

    # Sentiment method distribution
    from app.models import ArticleSentimentResult
    methods = {}
    for row in db.session.query(ArticleSentimentResult.method, db.func.count()).group_by(ArticleSentimentResult.method).all():
        methods[row[0]] = row[1]
    print(f"   Sentiment methods: {methods}")

    print("\n" + "=" * 60)
    print("🏁 End-to-end test complete")
    if all_ok:
        print("✅ All API fields OK")
    else:
        print("⚠️ Some fields missing (see above)")
