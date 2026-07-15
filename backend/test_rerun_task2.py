"""用新算法对 Task 2 全部已爬数据重跑分析管线"""
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    from app.models import Article, Event, Task
    from app.services.content_analysis_service import (
        create_analysis_run, run_content_analysis,
        _title_matches_keyword, _search_keyword_terms
    )
    from app.services.event_aggregation_service import (
        create_aggregation_run, run_event_aggregation, publish_cluster
    )
    from app.services.sentiment_analysis_service import (
        create_sentiment_run, run_sentiment_analysis
    )
    from app.models.event_aggregation import AggregationCluster

    task_id = 2
    kw = '长鑫科技上市'
    terms = _search_keyword_terms(kw)

    # ===== 1. 统计现状 =====
    print('=== 当前状态 ===')
    current_events = db.session.execute(text(
        'SELECT id, title, independent_report_count, platform_count FROM event WHERE source_task_id = :tid'
    ), {'tid': task_id}).fetchall()
    for ev in current_events:
        arts_cnt = db.session.execute(text(
            'SELECT COUNT(*) FROM article WHERE event_id = :eid'
        ), {'eid': ev[0]}).scalar()
        print(f'  Event {ev[0]}: {ev[1][:50]} reports={ev[2]} platforms={ev[3]} articles={arts_cnt}')

    # ===== 2. 获取全部已爬文章并重新筛选 =====
    all_articles = Article.query.filter_by(crawl_task_id=task_id).all()
    print(f'\n总爬取: {len(all_articles)} 篇')

    # 质量过滤
    qualified = []
    for a in all_articles:
        nlp = float(a.nlp_weight or 0)
        clen = len((a.clean_content or a.raw_content or '').strip())
        src_type = (a.source_type or '').strip().casefold()
        min_len = 30 if src_type == 'social' else 50
        if nlp >= 0.5 and clen >= min_len:
            qualified.append(a)
    print(f'质量合格: {len(qualified)} 篇 (排除 {len(all_articles)-len(qualified)} 篇)')

    # 关键词匹配
    kw_matched = [a for a in qualified if _title_matches_keyword(a.title or '', terms)]
    kw_failed = [a for a in qualified if a not in kw_matched]
    print(f'关键词匹配 (新jieba): {len(kw_matched)} 篇')
    print(f'关键词不匹配: {len(kw_failed)} 篇')

    # LLM 语义
    from app.services.content_analysis_service import _llm_batch_semantic_match
    llm_candidates = [(a.id, a.title or '') for a in kw_failed]
    print(f'LLM 检查候选: {len(llm_candidates)} 篇...')
    llm_rescued_ids = _llm_batch_semantic_match(kw, llm_candidates)
    print(f'LLM 挽救: {len(llm_rescued_ids)} 篇')

    # 最终
    final_ids = [a.id for a in kw_matched] + list(llm_rescued_ids)
    print(f'\n最终提交分析: {len(final_ids)} 篇')

    # 分析提交的文章
    by_plat = {}
    for aid in sorted(final_ids):
        a = Article.query.get(aid)
        if a:
            by_plat[a.platform] = by_plat.get(a.platform, 0) + 1
    print('平台分布:')
    for p, c in sorted(by_plat.items(), key=lambda x: -x[1]):
        print(f'  {p}: {c}')

    # ===== 3. 运行分析管线 =====
    user_id = db.session.execute(text(
        'SELECT created_by FROM task WHERE id = :tid'
    ), {'tid': task_id}).scalar()

    print('\n' + '=' * 60)
    print('--- 内容分析 ---')
    ar, reused = create_analysis_run(
        final_ids,
        user_id=user_id,
        mode='search',
        keyword=kw,
        platforms=['bilibili','zhihu','weibo','xiaohongshu','douyin',
                    'news_sspai','news_infoq','news_thepaper','news_36kr',
                    'news_people','baidu_news'],
        source_task_id=task_id,
    )
    print(f'AnalysisRun id={ar.id} reused={reused} status={ar.status} articles={ar.article_count} rep={ar.representative_count}')
    if ar.warnings:
        for w in ar.warnings:
            print(f'  ⚠ {w}')

    if ar.status != 'success':
        run_content_analysis(ar.id)
        ar_refresh = db.session.get(type(ar), ar.id)
        print(f'  运行后: status={ar_refresh.status} rep={ar_refresh.representative_count}')

    print('\n--- 事件聚合 ---')
    agr, agg_reused = create_aggregation_run(ar.id, user_id=user_id, source_task_id=task_id)
    print(f'AggregationRun id={agr.id} reused={agg_reused} status={agr.status}')

    if agr.status != 'success':
        run_event_aggregation(agr.id)
        agr_refresh = db.session.get(type(agr), agr.id)
        stats = (agr_refresh.statistics or {})
        print(f'  运行后: status={agr_refresh.status} clusters={stats.get("cluster_count","?")}')

    print('\n--- 情感分析 ---')
    sr, sr_reused = create_sentiment_run(agr.id, source_task_id=task_id, user_id=user_id)
    print(f'SentimentRun id={sr.id} reused={sr_reused} status={sr.status}')

    if sr.status != 'success':
        run_sentiment_analysis(sr.id)
        sr_refresh = db.session.get(type(sr), sr.id)
        s_stats = (sr_refresh.statistics or {})
        print(f'  运行后: status={sr_refresh.status} results={s_stats.get("result_count","?")}')

    print('\n--- 发布事件 ---')
    clusters = AggregationCluster.query.filter_by(aggregation_run_id=agr.id).all()
    print(f'聚类数: {len(clusters)}')

    publish_count = 0
    for cluster in clusters:
        try:
            result = publish_cluster(cluster.id, user_id=user_id)
            evt_id = result.get('event_id') if isinstance(result, dict) else None
            if evt_id:
                arts = Article.query.filter_by(event_id=evt_id).count()
                evt = Event.query.get(evt_id)
                print(f'  ✅ Event {evt_id}: "{evt.title[:50] if evt else "?"}" articles={arts}')
                publish_count += 1
            else:
                reused = result.get('reused') if isinstance(result, dict) else False
                print(f'  🔄 复用已有事件: {result}')
                publish_count += 1
        except Exception as e:
            import traceback
            print(f'  ❌ cluster {cluster.id} 发布失败: {e}')
            traceback.print_exc()
    print(f'发布事件数: {publish_count}')
    db.session.commit()

    # ===== 4. 最终统计 =====
    print('\n' + '=' * 60)
    print('=== 新旧对比 ===')
    print('=' * 60)

    # 新发布的事件
    new_events = db.session.execute(text(
        'SELECT id, title, independent_report_count, platform_count, heat_index, created_at '
        'FROM event WHERE source_task_id = :tid ORDER BY id DESC'
    ), {'tid': task_id}).fetchall()

    for ev in new_events:
        arts = db.session.execute(text(
            'SELECT COUNT(*) FROM article WHERE event_id = :eid'
        ), {'eid': ev[0]}).scalar()
        plat_dist = db.session.execute(text(
            'SELECT platform, COUNT(*) FROM article WHERE event_id = :eid GROUP BY platform ORDER BY COUNT(*) DESC'
        ), {'eid': ev[0]}).fetchall()
        plats = ', '.join(f'{p[0]}:{p[1]}' for p in plat_dist)
        print(f'\nEvent {ev[0]}: {ev[1]}')
        print(f'  文章: {arts} 篇 | 平台: {len(plat_dist)} 个 ({plats})')
        print(f'  热度: {ev[4]:.1f} | 创建: {ev[5]}')

    # 对比
    print('\n--- 对比 ---')
    old_arts = db.session.execute(text(
        'SELECT COUNT(DISTINCT id) FROM article WHERE event_id = 3'
    )).scalar()
    new_arts_total = sum(
        db.session.execute(text(
            'SELECT COUNT(*) FROM article WHERE event_id = :eid'
        ), {'eid': ev[0]}).scalar()
        for ev in new_events
    )
    print(f'旧方案: Event 3 = {old_arts} 篇文章')
    print(f'新方案: {len(new_events)} 个事件, 共 {new_arts_total} 篇文章')

print('\n✅ 完成')
