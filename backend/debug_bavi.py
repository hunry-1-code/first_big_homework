"""
全链路调试脚本 — 台风巴威舆情分析
用法: cd backend && .venv\Scripts\python debug_bavi.py
"""
import json
import sys
import os
import io

# Windows console UTF-8 fix
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

app = create_app()
client = app.test_client()

# ── 1. 登录获取 token ──
print("=" * 60)
print("🔑 Step 1: 登录")
resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
login_data = resp.get_json()
print(f"   登录结果: code={login_data.get('code')}, message={login_data.get('message')}")
token = login_data.get("data", {}).get("token")
if not token:
    print("   ❌ 登录失败，退出")
    sys.exit(1)
headers = {"Authorization": f"Bearer {token}"}
print(f"   ✅ Token: {token[:30]}...")

# ── 2. 触发关键词搜索 ──
print("\n" + "=" * 60)
print("🔍 Step 2: 触发关键词搜索「台风巴威」")
resp = client.post("/api/crawler/search",
                   json={"keyword": "台风巴威"},
                   headers=headers)
search_data = resp.get_json()
print(f"   响应: code={search_data.get('code')}, message={search_data.get('message')}")
search_result = search_data.get("data", {})
print(f"   task_id={search_result.get('task_id')}, reused={search_result.get('reused')}, cached={search_result.get('cached')}")

task_id = search_result.get("task_id")
if not task_id:
    print("   ❌ 没有 task_id，可能缓存命中或失败")
    if search_result.get("cached"):
        print("   ⚠️ 命中缓存，跳过采集（如需重新采集请清库）")
    sys.exit(0)

# ── 3. 查询任务结果 ──
print("\n" + "=" * 60)
print("📋 Step 3: 查询任务结果")
resp = client.get(f"/api/tasks/{task_id}", headers=headers)
task_data = resp.get_json()
task = task_data.get("data", {})
print(f"   status={task.get('status')}, progress={task.get('progress')}%")
print(f"   message={task.get('message')}")
result = task.get("result") or {}
print(f"   collected={result.get('collected')}, processed={result.get('processed')}, failed={result.get('failed')}")
print(f"   platform_counts={result.get('platform_counts')}")
errors = result.get("errors") or []
if errors:
    print(f"   ⚠️ 采集错误 ({len(errors)} 个):")
    for e in errors[:10]:
        print(f"      [{e.get('platform')}] {e.get('code')}: {e.get('message')[:100]}")

# ── 4. 检查事件列表 ──
print("\n" + "=" * 60)
print("📊 Step 4: 查询事件列表")
resp = client.get("/api/events?keyword=台风&size=20", headers=headers)
events_data = resp.get_json()
events = events_data.get("data", {}).get("events", [])
print(f"   事件总数: {events_data.get('data', {}).get('total', 0)}")
for i, event in enumerate(events):
    print(f"\n   ┌─ 事件 #{i+1}: id={event.get('id')}")
    print(f"   ├─ title: {event.get('title', '')[:60]}")
    print(f"   ├─ heat_index: {event.get('heat_index')}")
    print(f"   ├─ lifecycle_stage: {event.get('lifecycle_stage')}")
    print(f"   ├─ sentiment: +{event.get('sentiment_positive')} / -{event.get('sentiment_negative')} / ~{event.get('sentiment_neutral')}")
    print(f"   ├─ hot_rank: {event.get('hot_rank')}")
    print(f"   ├─ platform_count: {event.get('platform_count')}")
    print(f"   ├─ report_count: {event.get('independent_report_count')}")
    print(f"   └─ time_confidence: {event.get('time_confidence')}")

if not events:
    print("   ⚠️ 没有任何事件！可能采集或聚合环节出了严重问题。")

# ── 5. 检查事件详情（取第一个事件） ──
print("\n" + "=" * 60)
print("🔎 Step 5: 查询事件详情")
if events:
    event_id = events[0]["id"]
    resp = client.get(f"/api/events/{event_id}", headers=headers)
    detail = resp.get_json().get("data", {})

    def _check(key, desc=""):
        val = detail.get(key)
        status = "✅" if val else "❌ 空/缺失"
        extra = ""
        if isinstance(val, list):
            extra = f" ({len(val)} 条)"
        elif isinstance(val, dict):
            extra = f" ({len(val)} 个字段)"
        elif isinstance(val, str) and len(val) > 60:
            extra = f" 内容={val[:60]}..."
        elif val is not None:
            extra = f" = {val}" if not isinstance(val, (list, dict)) else ""
        print(f"   {status} {key:25s} {desc}{extra}")

    print("\n   ── 基础字段 ──")
    _check("id")
    _check("title")
    _check("summary")
    _check("heat_index")
    _check("core_heat")
    _check("spread_heat")
    _check("is_hot")
    _check("hot_rank")
    _check("lifecycle_stage")
    _check("time_confidence")
    _check("first_publish_time")
    _check("last_activity_time")

    print("\n   ── 情感字段 ──")
    _check("sentiment_positive")
    _check("sentiment_negative")
    _check("sentiment_neutral")

    print("\n   ── 嵌套数据块 ──")
    report = detail.get("report") or {}
    print(f"   {'✅' if report.get('overview_text') else '❌'} report.overview_text")
    print(f"   {'✅' if report.get('risk_data') else '❌'} report.risk_data")
    if report.get("risk_data"):
        rd = report["risk_data"]
        print(f"      score={rd.get('score')}, level={rd.get('level')}, factors={rd.get('factors')}")

    trend = detail.get("trend") or {}
    print(f"   {'✅' if trend.get('dates') else '❌'} trend.dates ({len(trend.get('dates') or [])} 个)")
    print(f"   {'✅' if trend.get('counts') else '❌'} trend.counts ({len(trend.get('counts') or [])} 个)")
    print(f"   {'✅' if trend.get('key_points') else '❌'} trend.key_points ({len(trend.get('key_points') or [])} 个)")

    sentiment = detail.get("sentiment") or {}
    print(f"   {'✅' if sentiment else '❌'} sentiment 块")
    if sentiment:
        print(f"      positive={sentiment.get('positive')}, negative={sentiment.get('negative')}")
        daily = sentiment.get("daily") or sentiment.get("daily_trend") or []
        print(f"      daily_trend: {len(daily)} 天")
        platforms = sentiment.get("platform_distribution") or []
        print(f"      platform_distribution: {len(platforms)} 个平台")

    platform = detail.get("platform") or {}
    print(f"   {'✅' if platform.get('platforms') else '❌'} platform.platforms ({len(platform.get('platforms') or [])} 个)")

    keywords = detail.get("keywords") or {}
    kw_list = keywords.get("keywords") or []
    print(f"   {'✅' if kw_list else '❌'} keywords.keywords ({len(kw_list)} 个)")

    articles = detail.get("articles") or {}
    art_list = articles.get("articles") or []
    print(f"   {'✅' if art_list else '❌'} articles.articles ({len(art_list)} 篇)")

    # ── 6. 检查传播图谱 ──
    print("\n" + "=" * 60)
    print("🔗 Step 6: 查询传播图谱")
    resp = client.get(f"/api/events/{event_id}/propagation", headers=headers)
    prop = resp.get_json().get("data", {})
    key_nodes = prop.get("key_nodes") or []
    graph = prop.get("graph") or {}
    print(f"   key_nodes: {len(key_nodes)} 个")
    for n in key_nodes:
        print(f"      [{n.get('type')}] {n.get('author', '')[:20]} @ {n.get('platform', '')}")
    nodes = graph.get("nodes") or []
    links = graph.get("links") or []
    print(f"   graph.nodes: {len(nodes)}")
    print(f"   graph.links: {len(links)}")
else:
    print("   跳过（无事件）")

# ── 7. 查文章表直接验证 ──
print("\n" + "=" * 60)
print("📰 Step 7: 直接查 Article 表验证预处理质量")
from app.extensions import db
from app.models import Article
with app.app_context():
    total = Article.query.count()
    cleaned = Article.query.filter(Article.clean_status == "success").count()
    dup = Article.query.filter(Article.is_duplicate == True).count()
    with_sentiment = Article.query.filter(Article.sentiment_label.isnot(None)).count()
    print(f"   总文章数: {total}")
    print(f"   清洗成功: {cleaned}")
    print(f"   重复标记: {dup}")
    print(f"   已标情感: {with_sentiment}")
    print(f"   清洗版本分布:")
    for row in Article.query.with_entities(Article.clean_status, db.func.count()).group_by(Article.clean_status).all():
        print(f"      {row[0]}: {row[1]}")
    print(f"   平台分布:")
    for row in Article.query.with_entities(Article.platform, db.func.count()).group_by(Article.platform).all():
        print(f"      {row[0]}: {row[1]}")

# ── 8. 前后端对齐检查 ──
print("\n" + "=" * 60)
print("🎯 Step 8: 前端对齐检查")
if events:
    print("\n   前端 detail.vue 需要的字段 vs 后端返回:")
    checks = [
        ("eventData.title", detail.get("title")),
        ("eventData.heat_index", detail.get("heat_index")),
        ("eventData.lifecycle_stage", detail.get("lifecycle_stage")),
        ("eventData.sentiment_positive", detail.get("sentiment_positive")),
        ("eventData.sentiment_negative", detail.get("sentiment_negative")),
        ("eventData.sentiment_neutral", detail.get("sentiment_neutral")),
        ("eventData.report.overview_text", (detail.get("report") or {}).get("overview_text")),
        ("eventData.report.risk_data", (detail.get("report") or {}).get("risk_data")),
        ("eventData.trend.dates", (detail.get("trend") or {}).get("dates")),
        ("eventData.trend.counts", (detail.get("trend") or {}).get("counts")),
        ("eventData.trend.key_points", (detail.get("trend") or {}).get("key_points")),
        ("eventData.sentiment (块)", detail.get("sentiment")),
        ("eventData.platform.platforms", (detail.get("platform") or {}).get("platforms")),
        ("eventData.keywords.keywords", (detail.get("keywords") or {}).get("keywords")),
        ("eventData.articles.articles", (detail.get("articles") or {}).get("articles")),
    ]
    for label, val in checks:
        ok = val is not None and val != [] and val != {} and val != "" and val != 0
        # 0 是合法值
        if isinstance(val, (int, float)):
            ok = True
        print(f"   {'✅' if ok else '❌'} {label}")

    # 特别检查：传播图是硬编码的
    print("\n   前端 buildPropagationData() 使用的硬编码数据 vs 后端实际数据:")
    print(f"      后端 key_nodes: {len(key_nodes)} 个")
    print(f"      后端 graph.nodes: {len(nodes)} 个")
    print(f"      后端 graph.links: {len(links)} 个")
    print(f"      ⚠️ 前端完全没用后端数据，用的是硬编码假节点！")

    # 情感趋势检查
    daily = (sentiment or {}).get("daily") or (sentiment or {}).get("daily_trend") or []
    print(f"\n   前端 initSentimentTrendChart() 使用的模拟数据 vs 后端实际数据:")
    print(f"      后端 sentiment.daily_trend: {len(daily)} 天")
    print(f"      ⚠️ 前端用 sin/cos 模拟，没用后端数据！")

print("\n" + "=" * 60)
print("🏁 全链路调试完成")
