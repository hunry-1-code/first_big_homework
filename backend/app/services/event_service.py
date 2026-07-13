from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy import or_

from app.analysis.fake_detector import _build_context, batch_assess_articles
from app.analysis.trend_predictor import get_lifecycle_change_points
from app.extensions import db
from app.models import AnalysisRunArticle, Article, Event, EventHeatSnapshot, Report
from app.services.event_similarity_service import search_historical_events
from app.services.api_contract_service import api_platform_name,api_lifecycle_stage,normalized_sentiment,api_sentiment_label,clamp_heat,clamp_ratio,short_date,trend_key_points

# 文章级关键词缓存（避免同一 event detail 请求中重复查询）
_keywords_cache: dict[int, list[dict]] = {}


def _article_keywords(article_id: int) -> list[dict]:
    """取单篇文章的 top-5 关键词（带 sentiment），带简单缓存。"""
    if article_id in _keywords_cache:
        return _keywords_cache[article_id]
    rows = AnalysisRunArticle.query.filter_by(article_id=article_id).all()
    for row in rows:
        if row.keywords and len(row.keywords) >= 3:
            result = []
            for kw in row.keywords[:5]:
                if isinstance(kw, dict) and kw.get("term"):
                    result.append({
                        "word": kw["term"].strip(),
                        "score": float(kw.get("score", 0)),
                        "sentiment": str(kw.get("sentiment", "neutral")),
                    })
            _keywords_cache[article_id] = result
            return result
    _keywords_cache[article_id] = []
    return []


def _event_keywords(event: Event) -> dict:
    """从 AnalysisRunArticle 聚合事件的关键词列表。

    策略：取每篇文章 TF-IDF 最高的关键词（跳过查询词），
    按平均 score × log(出现次数) 排序，cosine 归一化权重。
    """
    import math
    article_ids = [
        a.id for a in Article.query.filter_by(event_id=event.id)
        .with_entities(Article.id).limit(200).all()
    ]
    if not article_ids:
        return {"keywords": []}
    rows = AnalysisRunArticle.query.filter(
        AnalysisRunArticle.article_id.in_(article_ids)
    ).all()

    # 识别查询词（出现在超过半数文章中的 source=query 词）
    query_candidates: dict[str, int] = {}
    for row in rows:
        for kw in (row.keywords or []):
            if isinstance(kw, dict) and kw.get("source") == "query":
                term = kw["term"].strip()
                query_candidates[term] = query_candidates.get(term, 0) + 1
    unique_articles = len(article_ids)
    query_terms = {t for t, c in query_candidates.items() if c >= unique_articles * 0.5}

    # 聚合：每篇文章取 top-3 非查询词，收集 score/sentiment/entity_type
    from collections import Counter as _Cnt
    term_data: dict[str, dict] = {}
    for row in rows:
        seen: set[str] = set()
        take = 0
        for kw in (row.keywords or []):
            if not isinstance(kw, dict):
                continue
            term = kw["term"].strip()
            if term in query_terms or term in seen:
                continue
            if len(term) <= 1 or not any('一' <= c <= '鿿' for c in term):
                continue
            seen.add(term)
            if term not in term_data:
                term_data[term] = {"scores": [], "sentiments": [], "types": []}
            term_data[term]["scores"].append(float(kw.get("score", 0)))
            term_data[term]["sentiments"].append(str(kw.get("sentiment", "neutral")))
            term_data[term]["types"].append(str(kw.get("type", kw.get("entity_type", "concept"))))
            take += 1
            if take >= 3:
                break

    # 排序：log 频率 + 排名衰减权重
    ranked = []
    for term, data in term_data.items():
        cnt = len(data["scores"])
        avg_score = sum(data["scores"]) / cnt
        freq_log = math.log(1 + cnt)
        dom_s = _Cnt(data["sentiments"]).most_common(1)[0][0]
        dom_t = _Cnt(data["types"]).most_common(1)[0][0]
        ranked.append((term, freq_log, avg_score, cnt, dom_s, dom_t))

    ranked.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)
    ranked = ranked[:30]
    if not ranked:
        return {"keywords": []}

    total = len(ranked)
    return {
        "keywords": [
            {
                "word": term,
                "weight": round(1.0 - (idx / total) * 0.85, 4),
                "sentiment": sentiment,
                "entity_type": etype,
            }
            for idx, (term, freq_log, avg_score, cnt, sentiment, etype) in enumerate(ranked)
        ]
    }




def _extract_event_metadata(event, articles) -> dict:
    """用 LLM 一次提取事件的时间、地点、人物和起因。失败则回退规则提取。"""
    try:
        from flask import current_app
        from app.llm.client import LLMClient
        from app.llm.prompts import EVENT_SUMMARY_PROMPT
        client = LLMClient(
            api_key=current_app.config.get("LLM_API_KEY", ""),
            base_url=current_app.config.get("LLM_BASE_URL", ""),
            model_name=current_app.config.get("LLM_MODEL_NAME", ""),
            timeout=15,
        )
        samples = "\n".join(
            f"- [{a.platform}] {a.title}"
            for a in articles[:10] if a.title
        )
        resp = client.chat([
            {"role": "system", "content": EVENT_SUMMARY_PROMPT},
            {"role": "user", "content": (
                f"事件标题：{event.title or '未知'}\n相关报道：\n{samples}\n\n"
                "请返回 JSON：{\"time_code\":\"发生时间\",\"location\":\"地点\","
                "\"key_figures\":\"人物/机构\",\"cause\":\"起因概述(≤100字)\"}"
            )}
        ], temperature=0.3, max_tokens=200)
        import json, re
        text = resp["content"].strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1)
        value = json.loads(text)
        if isinstance(value, dict):
            return {
                "time_code": str(value.get("time_code", "")).strip()[:50],
                "location": str(value.get("location", "")).strip()[:100],
                "key_figures": str(value.get("key_figures", "")).strip()[:200],
                "cause": str(value.get("cause", "")).strip()[:200],
            }
    except Exception:
        pass
    # 规则回退
    return {
        "time_code": event.first_publish_time.strftime("%Y年%m月%d日 %H:%M") if event.first_publish_time else "",
        "location": "",
        "key_figures": "",
        "cause": "",
    }


def _event_item(event: Event, snapshot: EventHeatSnapshot | None = None, platforms: list[str] | None = None) -> dict:
    if snapshot is None and event.current_heat_snapshot_id:
        snapshot = db.session.get(EventHeatSnapshot, event.current_heat_snapshot_id)
    positive,negative,neutral=normalized_sentiment(event.sentiment_positive,event.sentiment_negative,event.sentiment_neutral)
    # 轻量 top-3 关键词（给看板卡片用）
    top3 = []
    try:
        ek = _event_keywords(event)
        top3 = [{"word": k["word"], "sentiment": k.get("sentiment", "neutral")}
                for k in (ek.get("keywords") or [])[:3]]
    except Exception:
        pass
    return {
        "id": event.id,
        "title": event.title,
        "summary": event.summary,
        "top_keywords": top3,
        "topic_category": event.topic_category,
        "topic_name": event.topic_name,
        "heat_index": clamp_heat(event.heat_index),
        "core_heat": float(event.core_heat or 0),
        "spread_heat": event.spread_heat,
        "is_hot": bool(event.is_hot),
        "hot_rank": event.hot_rank,
        "lifecycle_stage": api_lifecycle_stage(event.lifecycle_stage),
        "lifecycle_status": event.lifecycle_status,
        "lifecycle_confidence": float(event.lifecycle_confidence or 0),
        "lifecycle_evidence": event.lifecycle_evidence or {},
        "lifecycle_updated_at": (
            event.lifecycle_updated_at.isoformat()
            if event.lifecycle_updated_at
            else None
        ),
        "sentiment_positive": positive,
        "sentiment_negative": negative,
        "sentiment_neutral": neutral,
        "independent_report_count": int(event.independent_report_count or 0),
        "platform_count": int(event.platform_count or 0),
        "platforms": platforms or [],
        "time_confidence": event.time_confidence,
        "first_publish_time": event.first_publish_time.isoformat()
        if event.first_publish_time
        else None,
        "last_activity_time": event.last_activity_time.isoformat()
        if event.last_activity_time
        else None,
        "calculated_at": snapshot.calculated_at.isoformat() if snapshot else None,
        "formula_version": snapshot.formula_version if snapshot else None,
        "warnings": (snapshot.calculation_details or {}).get("warnings", [])
        if snapshot
        else ["HEAT_SNAPSHOT_UNAVAILABLE"],
    }


def list_events(args) -> dict:
    page = max(1, int(args.get("page", 1)))
    size = max(1, min(100, int(args.get("size", 20))))
    query = Event.query
    keyword = str(args.get("keyword") or "").strip()
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                Event.title.like(pattern),
                Event.topic_name.like(pattern),
                Event.summary.like(pattern),
            )
        )
    hot_value = str(args.get("hot") or "").strip().casefold()
    if hot_value in {"1", "true", "yes"}:
        query = query.filter(Event.is_hot.is_(True))
    total = query.count()
    events = (
        query.order_by(Event.is_hot.desc(), Event.hot_rank.asc(), Event.heat_index.desc(), Event.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    # 批量预加载 heat snapshots 和 platform 信息，避免 N+1 查询
    snapshot_ids = [e.current_heat_snapshot_id for e in events if e.current_heat_snapshot_id]
    snapshots_map = {}
    if snapshot_ids:
        snapshots = EventHeatSnapshot.query.filter(EventHeatSnapshot.id.in_(snapshot_ids)).all()
        snapshots_map = {s.id: s for s in snapshots}
    event_ids = [e.id for e in events]
    platform_rows = (
        db.session.query(Article.event_id, Article.platform)
        .filter(Article.event_id.in_(event_ids), Article.platform.isnot(None))
        .distinct()
        .all()
    ) if event_ids else []
    platforms_map: dict[int, list[str]] = {}
    for event_id, platform in platform_rows:
        mapped = api_platform_name(platform)
        if mapped:
            platforms_map.setdefault(event_id, []).append(mapped)
    return {
        "events": [_event_item(event, snapshots_map.get(event.current_heat_snapshot_id), platforms_map.get(event.id, [])) for event in events],
        "total": total,
        "page": page,
        "size": size,
    }


def get_event_detail(event_id: int) -> dict | None:
    _keywords_cache.clear()  # 每次新请求清缓存
    event = Event.query.get(event_id)
    if event is None:
        return None
    articles = (
        Article.query.filter_by(event_id=event.id)
        .order_by(Article.publish_time.desc())
        .limit(200)
        .all()
    )
    snapshots = (
        EventHeatSnapshot.query.filter_by(event_id=event.id)
        .order_by(EventHeatSnapshot.calculated_at)
        .all()
    )
    platform_counts = Counter(article.platform for article in articles)
    total_articles = sum(platform_counts.values())
    report = Report.query.filter_by(event_id=event.id).order_by(Report.id.desc()).first()
    from app.services.sentiment_analysis_service import get_event_sentiment

    sentiment = get_event_sentiment(event.id)
    data = _event_item(event)
    if snapshots:
        trend_dates = [item.calculated_at.isoformat() for item in snapshots]
        trend_counts = [
            (item.raw_statistics or {}).get("independent_report_count_7d", 0)
            for item in snapshots
        ]
        trend_heat = [item.final_heat for item in snapshots]
    else:
        # 无快照时从 article.publish_time 实时聚合
        from collections import OrderedDict

        daily = OrderedDict()
        for a in sorted(articles, key=lambda x: x.publish_time or datetime.min):
            if a.publish_time:
                day = a.publish_time.strftime("%Y-%m-%d")
                daily[day] = daily.get(day, 0) + 1
        trend_dates = list(daily.keys())
        trend_counts = list(daily.values())
        trend_heat = trend_counts  # fallback: 热度=报道量
    lifecycle_points = get_lifecycle_change_points(trend_counts, trend_dates)
    # 计算事件级风险摘要
    ctx = _build_context(event.id, articles)
    article_risks = batch_assess_articles(articles, ctx)
    # 将评估结果持久化到 Article 模型
    for article, risk in zip(articles, article_risks):
        if getattr(article, "is_suspicious", None) != risk["is_suspicious"] or \
           getattr(article, "suspicious_score", None) != risk["score"]:
            article.is_suspicious = risk["is_suspicious"]
            article.suspicious_score = risk["score"]
            article.suspicious_reason = risk["reason"]
            article.suspicious_method = risk["method"]
    db.session.commit()
    suspicious_articles = [r for r in article_risks if r["is_suspicious"]]
    avg_risk = sum(r["score"] for r in article_risks) / len(article_risks) if article_risks else 0
    risk_data = {
        "score": round(avg_risk, 1),
        "level": "高风险" if avg_risk >= 70 else "中风险" if avg_risk >= 40 else "低风险",
        "suspicious_count": len(suspicious_articles),
        "total_count": len(article_risks),
        "factors": list(set(
            reason for r in article_risks
            for reason in r["reason"].split("; ")
            if reason and "未发现" not in reason
        ))[:5],
    }

    # ── AI 元数据：从 articles 聚合 ──
    # AI 元数据：优先用 LLM 提取，失败回退 DB 已有值
    ai_meta = _extract_event_metadata(event, articles)
    data["time_code"] = ai_meta["time_code"] if not event.time_code else event.time_code
    data["location"] = event.location or ai_meta["location"]
    data["key_figures"] = event.key_figures or ai_meta["key_figures"]
    data["cause"] = event.cause or ai_meta["cause"]

    data.update(
        report={
            "overview_text": report.overview_text if report else event.summary,
            "risk_data": report.risk_data if (report and report.risk_data) else risk_data,
        },
        trend={
            "dates": [short_date(value) for value in trend_dates[-14:]],
            "counts": trend_counts[-14:],
            "heat": trend_heat,
            "key_points": trend_key_points([short_date(value) for value in trend_dates[-14:]],trend_counts[-14:]),
        },
        sentiment=sentiment,
        platform={
            "platforms": [
                {
                    "platform": api_platform_name(platform),
                    "count": count,
                    "percentage": count / total_articles if total_articles else 0,
                }
                for platform, count in sorted(platform_counts.items()) if api_platform_name(platform)
            ]
        },
        keywords=_event_keywords(event),
        articles={
            "articles": [
                {
                    "id": article.id,
                    "platform": api_platform_name(article.platform) or "百度搜索",
                    "title": article.title,
                    "clean_content": article.clean_content,
                    "author": article.author,
                    "reposts_count": int(article.reposts_count or 0),
                    "comments_count": int(article.comments_count or 0),
                    "likes_count": int(article.likes_count or 0),
                    "sentiment_label": api_sentiment_label(article.sentiment_label),
                    "is_suspicious": bool(article.is_suspicious),
                    "suspicious_score": clamp_ratio((article.suspicious_score or 0)/100 if (article.suspicious_score or 0)>1 else article.suspicious_score),
                    "publish_time": article.publish_time.isoformat()
                    if article.publish_time
                    else None,
                    "keywords": _article_keywords(article.id),
                }
                for article in articles
            ],
            "total": len(articles),
        },
    )
    return data


def get_propagation_data(event_id: int) -> dict | None:
    """获取事件传播路径数据，包含关键节点和图结构。

    规格依据：项目需求规格说明书 §6.2 事件溯源与关键传播路径
    """
    event = Event.query.get(event_id)
    if event is None:
        return None

    articles = Article.query.filter_by(event_id=event.id)\
        .order_by(Article.publish_time.asc()).all()

    from app.propagation import build_propagation_graph
    from app.services.api_contract_service import api_platform_name
    return build_propagation_graph(articles, platform_mapper=api_platform_name)


def delete_event(event_id: int) -> None:
    from app.models import EventArticleMembership, EventSentimentSnapshot, EventHeatSnapshot
    event = db.session.get(Event, event_id)
    if event is None:
        raise KeyError(f"event not found: {event_id}")
    EventArticleMembership.query.filter_by(event_id=event_id).delete()
    EventSentimentSnapshot.query.filter_by(event_id=event_id).delete()
    EventHeatSnapshot.query.filter_by(event_id=event_id).delete()
    db.session.delete(event)
    db.session.commit()


def search_events(keyword: str) -> list[dict]:
    semantic = search_historical_events(keyword, limit=20)
    if not semantic:
        return list_events({"keyword": keyword, "page": 1, "size": 20})["events"]
    output = []
    for item in semantic:
        event = db.session.get(Event, item["event_id"])
        if event is None:
            continue
        value = _event_item(event)
        value["similarity"] = item["similarity"]
        value["match_reasons"] = item["match_reasons"]
        output.append(value)
    return output
