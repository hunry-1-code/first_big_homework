"""快速重跑分析流水线——复用已有爬虫数据，跳过爬取"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from app import create_app
app = create_app()

with app.app_context():
    from app.extensions import db
    from app.models import Article
    from app.services.content_analysis_service import create_analysis_run, run_content_analysis
    from app.services.event_aggregation_service import create_aggregation_run, run_event_aggregation
    from app.services.sentiment_analysis_service import create_sentiment_run, run_sentiment_analysis

    # 获取已有文章
    articles = Article.query.filter(Article.clean_status == "success").all()
    article_ids = [a.id for a in articles]
    platforms = list(set(a.platform for a in articles))
    print(f"已有文章: {len(articles)} 篇, 平台: {platforms}")

    # 1. 内容分析
    print("\n1. 内容分析 (TF-IDF + BGE)...")
    ar, reused = create_analysis_run(article_ids, mode="search", keyword="台风巴威", platforms=platforms)
    print(f"   AnalysisRun id={ar.id} reused={reused}")
    if not reused or ar.status != "success":
        result = run_content_analysis(ar.id)
        print(f"   result: {result}")
    else:
        print(f"   复用已有结果")

    # 检查 BGE
    from app.models import ArticleEmbedding
    emb_count = ArticleEmbedding.query.count()
    print(f"   BGE embeddings: {emb_count}")

    # 2. 事件聚合
    print("\n2. 事件聚合...")
    agr, reused = create_aggregation_run(ar.id)
    print(f"   AggregationRun id={agr.id} reused={reused} scope={agr.scope}")
    if not reused or agr.status != "success":
        result = run_event_aggregation(agr.id)
        print(f"   result: {result}")
    else:
        print(f"   复用已有结果")

    from app.models import AggregationCluster, AggregationRun
    agr_fresh = db.session.get(AggregationRun, agr.id)
    clusters = AggregationCluster.query.filter_by(aggregation_run_id=agr.id).order_by(AggregationCluster.cluster_index).all()
    print(f"   簇总数: {len(clusters)}")
    # 成员分布
    member_counts = [c.member_count for c in clusters]
    from collections import Counter
    dist = Counter(member_counts)
    print(f"   簇成员数分布: {dict(sorted(dist.items()))}")
    for c in clusters[:8]:
        print(f"   [{c.cluster_index}] members={c.member_count} title={c.title[:60] if c.title else 'N/A'} event_id={c.resolved_event_id}")

    # 3. 情感分析
    print("\n3. 情感分析...")
    sr, reused = create_sentiment_run(agr.id)
    print(f"   SentimentRun id={sr.id} reused={reused}")
    if not reused or sr.status != "success":
        result = run_sentiment_analysis(sr.id)
        print(f"   result: {result}")
    else:
        print(f"   复用已有结果")

    # 4. 检查事件
    from app.models import Event
    events = Event.query.all()
    print(f"\n4. 事件: {len(events)} 个")
    for e in events:
        print(f"   id={e.id} title={e.title[:60]} heat={e.heat_index}")

    # 5. 如果没有Event，尝试 publish 最大簇
    if not events and clusters:
        print("\n5. 尝试 publish 最大的簇...")
        try:
            from app.services.event_aggregation_service import publish_cluster
            biggest = max(clusters, key=lambda c: c.member_count)
            result = publish_cluster(biggest.id, user_id=1)
            print(f"   publish result: {result}")
        except Exception as e:
            print(f"   publish failed: {e}")

        events2 = Event.query.all()
        print(f"   发布后事件: {len(events2)} 个")
        for e in events2:
            print(f"   id={e.id} title={e.title[:60] if e.title else 'N/A'} heat={e.heat_index} is_hot={e.is_hot}")

    # 6. 最终检查 API 数据
    if Event.query.count() > 0:
        print("\n6. 测试 API 响应...")
        from app.services.event_service import get_event_detail
        event = Event.query.first()
        detail = get_event_detail(event.id)
        checks = [
            ("title", detail.get("title")),
            ("heat_index", detail.get("heat_index")),
            ("lifecycle_stage", detail.get("lifecycle_stage")),
            ("sentiment_positive", detail.get("sentiment_positive")),
            ("sentiment_negative", detail.get("sentiment_negative")),
            ("sentiment_neutral", detail.get("sentiment_neutral")),
            ("report.overview_text", (detail.get("report") or {}).get("overview_text")),
            ("report.risk_data", (detail.get("report") or {}).get("risk_data")),
            ("trend.dates", (detail.get("trend") or {}).get("dates")),
            ("trend.counts", (detail.get("trend") or {}).get("counts")),
            ("trend.key_points", (detail.get("trend") or {}).get("key_points")),
            ("sentiment block", detail.get("sentiment")),
            ("platform.platforms", (detail.get("platform") or {}).get("platforms")),
            ("keywords.keywords", (detail.get("keywords") or {}).get("keywords")),
            ("articles.articles", (detail.get("articles") or {}).get("articles")),
        ]
        for label, val in checks:
            ok = val is not None and val != [] and val != {} and val != ""
            if isinstance(val, (int, float)):
                ok = True
            print(f"   {'OK' if ok else 'MISS'} {label}")
    else:
        print("\n6. 跳过 API 检查（无 Event）")

    print("\nDone.")
