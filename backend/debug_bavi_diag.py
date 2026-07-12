"""补充诊断：查询分析中间表"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from app import create_app
app = create_app()

with app.app_context():
    from app.extensions import db
    from app.models import (
        AnalysisRun, AnalysisRunArticle,
        AggregationRun, AggregationCluster, AggregationAssignment,
        SentimentRun, ArticleSentimentResult,
        Event, EventArticleMembership,
        Article, ArticleEmbedding, DocumentFeatures,
        HotspotRun, TopicResult, Report
    )

    print("=" * 60)
    print("AnalysisRun:")
    for r in AnalysisRun.query.all():
        print(f"  id={r.id} status={r.status} mode={r.mode} keyword={r.keyword}")
        print(f"    articles={r.article_count} representative={r.representative_count}")
        print(f"    error={r.error_code}: {r.error_message}")
        ras = AnalysisRunArticle.query.filter_by(analysis_run_id=r.id).order_by(AnalysisRunArticle.id).limit(3).all()
        for ra in ras:
            print(f"    -> article_id={ra.article_id} feature_status={ra.feature_status} keywords={[(kw.get('term',''), round(kw.get('score',0),3)) for kw in (ra.keywords or [])[:3]]}")

    print("\n" + "=" * 60)
    print("AggregationRun:")
    for r in AggregationRun.query.all():
        print(f"  id={r.id} status={r.status} scope={r.scope} mode={r.mode}")
        print(f"    statistics={r.statistics}")
        print(f"    error={r.error_code}: {r.error_message}")
    clusters = AggregationCluster.query.all()
    print(f"  Total clusters: {len(clusters)}")
    for c in clusters[:5]:
        print(f"    cluster idx={c.cluster_index} title={c.title[:50] if c.title else 'N/A'} members={c.member_count} resolved_event_id={c.resolved_event_id}")

    print("\n" + "=" * 60)
    print("SentimentRun:")
    for r in SentimentRun.query.all():
        print(f"  id={r.id} status={r.status} scope={r.scope}")
        print(f"    statistics={r.statistics}")
        results = ArticleSentimentResult.query.filter_by(sentiment_run_id=r.id).limit(5).all()
        for s in results:
            print(f"    -> article_id={s.article_id} label={s.label} score={s.score} method={s.method}")

    print("\n" + "=" * 60)
    print("Events:")
    events = Event.query.all()
    print(f"  Total: {len(events)}")
    for e in events:
        print(f"  id={e.id} title={e.title[:60] if e.title else 'N/A'}")
        members = EventArticleMembership.query.filter_by(event_id=e.id).count()
        print(f"    members={members} heat={e.heat_index} is_hot={e.is_hot}")

    print("\n" + "=" * 60)
    print("Embeddings:")
    emb_count = ArticleEmbedding.query.count()
    print(f"  Total embeddings: {emb_count}")
    if emb_count > 0:
        first = ArticleEmbedding.query.first()
        print(f"  First: article_id={first.article_id} dimension={first.dimension} model={first.model_name}")

    print("\n" + "=" * 60)
    print("Reports:")
    reports = Report.query.all()
    print(f"  Total: {len(reports)}")
    for rp in reports:
        print(f"    event_id={rp.event_id} overview={'YES' if rp.overview_text else 'NO'}")

    print("\n" + "=" * 60)
    print("HotspotRun:")
    for r in HotspotRun.query.all():
        print(f"  id={r.id} status={r.status} topic_status={r.topic_status} heat_status={r.heat_status}")
        topics = TopicResult.query.filter_by(hotspot_run_id=r.id).all()
        print(f"    topics: {len(topics)}")
        for t in topics[:3]:
            print(f"    -> {t.category}: {t.topic_name} ({t.document_count} docs)")

    # 检查 task result
    print("\n" + "=" * 60)
    print("Task Detail:")
    from app.services.task_service import get_task
    task = get_task(1)
    if task:
        result = task.get("result") or {}
        print(f"  status={task.get('status')}")
        print(f"  analysis_run_id={result.get('analysis_run_id')}")
        print(f"  aggregation_run_id={result.get('aggregation_run_id')}")
        print(f"  sentiment_run_id={result.get('sentiment_run_id')}")
        print(f"  search_cache_expires_at={result.get('search_cache_expires_at')}")
