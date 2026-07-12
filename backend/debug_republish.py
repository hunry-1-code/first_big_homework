"""清旧事件 + publish 新 3 簇 + 重跑 E2E"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from app import create_app
app = create_app()

with app.app_context():
    from app.extensions import db
    from app.models import Event, EventArticleMembership, AggregationCluster, Article
    from app.services.event_aggregation_service import publish_cluster, run_event_aggregation
    from app.services.event_service import get_event_detail, get_propagation_data
    from app.services.sentiment_analysis_service import get_event_sentiment

    # 1. 清旧事件
    print("1. Clean old events...")
    EventArticleMembership.query.delete()
    Event.query.delete()
    Article.query.update({Article.event_id: None})
    db.session.commit()
    print(f"   Events: {Event.query.count()}, Memberships: {EventArticleMembership.query.count()}")

    # 2. Publish 3 个新簇
    clusters = AggregationCluster.query.filter_by(aggregation_run_id=3).order_by(AggregationCluster.member_count.desc()).all()
    print(f"\n2. Publishing {len(clusters)} clusters (members: {[c.member_count for c in clusters]})...")
    for c in clusters:
        try:
            r = publish_cluster(c.id, user_id=1)
            print(f"   [{c.cluster_index}] members={c.member_count} -> event_id={r.get('event_id')}")
        except Exception as e:
            print(f"   [{c.cluster_index}] FAILED: {e}")

    events = Event.query.all()
    linked = Article.query.filter(Article.event_id.isnot(None)).count()
    print(f"\n3. Results: {len(events)} events, {linked}/{Article.query.count()} articles linked")

    # 4. API 验证
    print("\n4. API quality check:")
    for e in events:
        d = get_event_detail(e.id)
        s = get_event_sentiment(e.id)
        p = get_propagation_data(e.id)
        art_count = len((d.get("articles") or {}).get("articles") or [])
        kw_count = len((d.get("keywords") or {}).get("keywords") or [])
        plat_count = len((d.get("platform") or {}).get("platforms") or [])
        nodes = len((p.get("graph") or {}).get("nodes") or [])
        links = len((p.get("graph") or {}).get("links") or [])
        daily = len((s or {}).get("daily") or [])
        print(f"   Event #{e.id}: {art_count} articles, {kw_count} keywords, {plat_count} platforms, {nodes} nodes, {links} links, {daily} daily")
        print(f"     title: {e.title[:80]}")
        print(f"     sentiment: +{e.sentiment_positive}/-{e.sentiment_negative}/~{e.sentiment_neutral}")
        print(f"     heat={e.heat_index} lifecycle={e.lifecycle_stage}")

    print("\n5. Done!")
