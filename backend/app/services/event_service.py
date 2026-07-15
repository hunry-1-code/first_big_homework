from __future__ import annotations

import json
import re
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
EVENT_METADATA_VERSION = "event-metadata-v2"


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


def _merged_keywords(event: Event, public_opinion: dict | None = None) -> dict:
    """合并文章关键词 + 公众评论高频词，统一用于词云展示。"""
    article_kws = _event_keywords(event)
    keywords = list(article_kws.get("keywords") or [])

    # 合并公众评论高频词（source=comment，权重按频次归一化）
    if public_opinion:
        pub_kws = public_opinion.get("public_keywords") or []
        if pub_kws:
            max_count = max(kw["count"] for kw in pub_kws) if pub_kws else 1
            for kw in pub_kws[:10]:
                # 去重：已在文章关键词中的跳过
                if any(k.get("word") == kw["word"] for k in keywords):
                    continue
                keywords.append({
                    "word": kw["word"],
                    "weight": round(kw["count"] / max_count, 4),
                    "sentiment": "neutral",  # 评论词无情感标注，默认中性
                    "source": "comment",
                })

    # 按权重降序排列
    keywords.sort(key=lambda k: k.get("weight", 0), reverse=True)
    return {"keywords": keywords}


def _event_keywords(event: Event) -> dict:
    """从 AnalysisRunArticle 聚合事件的关键词列表。

    策略：取每篇文章 TF-IDF 最高的事件特异词，按频率和分数排序；
    查询词保留为 source=query，但展示权重低于最高事件特异词。
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

    # 聚合：每篇文章取 top-3 事件词；查询词单独保留并降权。
    from collections import Counter as _Cnt
    term_data: dict[str, dict] = {}
    query_data: dict[str, dict] = {}
    for row in rows:
        seen: set[str] = set()
        take = 0
        for kw in (row.keywords or []):
            if not isinstance(kw, dict):
                continue
            term = kw["term"].strip()
            if term in seen:
                continue
            if term in query_terms:
                seen.add(term)
                if term not in query_data:
                    query_data[term] = {
                        "scores": [],
                        "sentiments": [],
                        "types": [],
                    }
                query_data[term]["scores"].append(float(kw.get("score", 0)))
                query_data[term]["sentiments"].append(
                    str(kw.get("sentiment", "neutral"))
                )
                query_data[term]["types"].append(
                    str(kw.get("type", kw.get("entity_type", "concept")))
                )
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
    ranked = ranked[: max(0, 30 - len(query_data))]
    if not ranked and not query_data:
        return {"keywords": []}

    total = max(1, len(ranked))
    output = [
            {
                "word": term,
                "weight": round(1.0 - (idx / total) * 0.85, 4),
                "sentiment": sentiment,
                "entity_type": etype,
                "source": "event",
            }
            for idx, (term, freq_log, avg_score, cnt, sentiment, etype) in enumerate(ranked)
        ]
    highest_event_weight = output[0]["weight"] if output else 1.0
    query_weight = min(0.6, highest_event_weight * 0.6)
    for index, (term, data) in enumerate(sorted(query_data.items())):
        sentiment = _Cnt(data["sentiments"]).most_common(1)[0][0]
        entity_type = _Cnt(data["types"]).most_common(1)[0][0]
        output.append(
            {
                "word": term,
                "weight": round(max(0.2, query_weight - index * 0.05), 4),
                "sentiment": sentiment,
                "entity_type": entity_type,
                "source": "query",
            }
        )
    return {"keywords": output}




def _extract_event_metadata(event, articles, *, client=None) -> dict:
    """Extract evidence-linked fields; failures return structured warnings."""
    try:
        if client is None:
            from flask import current_app
            from app.llm.client import LLMClient

            client = LLMClient(
                api_key=current_app.config.get("LLM_API_KEY", ""),
                base_url=current_app.config.get("LLM_BASE_URL", ""),
                model_name=current_app.config.get("LLM_MODEL_NAME", ""),
                timeout=15,
            )
        from app.llm.prompts import EVENT_METADATA_PROMPT

        allowed_ids = {int(article.id) for article in articles if article.id is not None}
        samples = [
            {
                "article_id": int(article.id),
                "platform": article.platform,
                "title": article.title,
                "content_excerpt": (article.clean_content or "")[:300],
                "publish_time": article.publish_time.isoformat()
                if article.publish_time
                else None,
            }
            for article in articles[:10]
            if article.id is not None
        ]
        resp = client.chat([
            {"role": "system", "content": EVENT_METADATA_PROMPT},
            {"role": "user", "content": (
                json.dumps(
                    {
                        "event_title": event.title or "未知",
                        "first_publish_time": event.first_publish_time.isoformat()
                        if event.first_publish_time
                        else None,
                        "articles": samples,
                    },
                    ensure_ascii=False,
                )
            )}
        ], temperature=0, max_tokens=500)
        text = str(resp.get("content", "")).strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("metadata response must be an object")
        limits = {"time_code": 50, "location": 100, "key_figures": 500, "cause": 500}
        fields = {}
        for name, limit in limits.items():
            item = value.get(name)
            if not isinstance(item, dict):
                continue
            field_value = " ".join(str(item.get("value") or "").split())[:limit]
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence") or 0)))
            except (TypeError, ValueError):
                confidence = 0.0
            evidence_ids = []
            for raw_id in item.get("evidence_article_ids") or []:
                try:
                    article_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if article_id in allowed_ids and article_id not in evidence_ids:
                    evidence_ids.append(article_id)
            fields[name] = {
                "value": field_value,
                "confidence": round(confidence, 6),
                "evidence_article_ids": evidence_ids,
            }
        return {
            "fields": fields,
            "model": resp.get("model") or getattr(client, "model_name", None),
            "warnings": [],
        }
    except Exception as exc:
        return {
            "fields": {},
            "model": None,
            "warnings": [f"LLM_METADATA_FAILED:{type(exc).__name__}"],
        }


def update_event_metadata(
    event: Event,
    articles: list[Article],
    *,
    now: datetime,
    client=None,
    client_factory=None,
) -> bool:
    """Persist metadata when the representative article set materially changes."""
    source_articles = [article for article in articles if not article.is_duplicate] or articles
    source_ids = sorted(int(article.id) for article in source_articles if article.id is not None)
    existing_evidence = dict(event.metadata_evidence or {})
    if (
        event.metadata_version == EVENT_METADATA_VERSION
        and event.metadata_status in {"success", "fallback"}
        and existing_evidence.get("source_article_ids") == source_ids
    ):
        return False

    if client is None and client_factory is not None:
        client = client_factory()
    extracted = _extract_event_metadata(event, source_articles, client=client)
    fields = extracted.get("fields") or {}
    warnings = list(extracted.get("warnings") or [])
    field_evidence = dict(existing_evidence.get("fields") or {})

    deterministic_time = (
        event.first_publish_time.strftime("%Y年%m月%d日 %H:%M")
        if event.first_publish_time
        else ""
    )
    llm_time = str((fields.get("time_code") or {}).get("value") or "").strip()
    if deterministic_time:
        if llm_time and llm_time != deterministic_time:
            warnings.append("TIME_CODE_CONFLICT")
        event.time_code = deterministic_time
        earliest_ids = [
            int(article.id)
            for article in source_articles
            if article.id is not None
            and article.publish_time == event.first_publish_time
        ]
        field_evidence["time_code"] = {
            "source": "first_publish_time",
            "confidence": 1.0,
            "evidence_article_ids": earliest_ids,
        }
    elif llm_time:
        event.time_code = llm_time
        field_evidence["time_code"] = {**fields["time_code"], "source": "llm"}

    for name in ("location", "key_figures", "cause"):
        item = fields.get(name) or {}
        value = str(item.get("value") or "").strip()
        if value:
            setattr(event, name, value)
            field_evidence[name] = {**item, "source": "llm"}

    confidences = [
        float(item.get("confidence") or 0)
        for name, item in field_evidence.items()
        if getattr(event, name, None)
    ]
    event.metadata_status = "success" if any(
        str((fields.get(name) or {}).get("value") or "").strip()
        for name in ("location", "key_figures", "cause")
    ) else "fallback"
    event.metadata_version = EVENT_METADATA_VERSION
    event.metadata_confidence = round(
        sum(confidences) / len(confidences) if confidences else 0.0,
        6,
    )
    event.metadata_evidence = {
        "fields": field_evidence,
        "warnings": sorted(set(warnings)),
        "source_article_ids": source_ids,
        "model": extracted.get("model"),
    }
    event.metadata_updated_at = now
    return True


def _rule_based_risk(event, articles) -> dict:
    """规则回退：没有 LLM 报告时，用 fake_detector 分数推算风险等级。"""
    suspicious = [a for a in articles if getattr(a, "is_suspicious", False)]
    s_count = len(suspicious)
    total = len(articles) or 1
    s_ratio = s_count / total

    # 平均可疑分数
    scores = [float(getattr(a, "suspicious_score", 0) or 0) for a in articles]
    avg_score = sum(scores) / len(scores) if scores else 0

    # 综合风险分：可疑率 60% + 平均分 40%
    risk_score = round(s_ratio * 60 + avg_score * 40, 1)

    if risk_score >= 50:
        level = "高风险"
    elif risk_score >= 25:
        level = "中风险"
    else:
        level = "低风险"

    factors = []
    if s_ratio > 0.2:
        factors.append("可疑报道占比较高")
    if avg_score > 0.3:
        factors.append("文章可疑度平均分较高")
    if total < 5:
        factors.append("报道总量偏低，可能存在信息不完整")
    if not factors:
        factors.append("未检测到明显风险因素")

    return {
        "level": level,
        "score": risk_score,
        "total_count": total,
        "suspicious_count": s_count,
        "factors": factors,
        "source": "rule_fallback",
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
    from app.services.lifecycle_prediction_service import build_prediction_payload
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
        "prediction": build_prediction_payload(event),
        "time_code": event.time_code,
        "location": event.location,
        "key_figures": event.key_figures,
        "cause": event.cause,
        "metadata_status": event.metadata_status,
        "metadata_version": event.metadata_version,
        "metadata_confidence": float(event.metadata_confidence or 0),
        "metadata_evidence": event.metadata_evidence or {},
        "metadata_updated_at": (
            event.metadata_updated_at.isoformat()
            if event.metadata_updated_at
            else None
        ),
        "sentiment_positive": positive,
        "sentiment_negative": negative,
        "sentiment_neutral": neutral,
        "independent_report_count": int(event.independent_report_count or 0),
        "platform_count": int(event.platform_count or 0),
        "platforms": platforms or [],
        "search_keyword": event.search_keyword,
        "source_task_id": event.source_task_id,
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
                Event.search_keyword.like(pattern),
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
    from app.services.public_opinion_service import get_public_opinion_snapshot
    public_opinion = get_public_opinion_snapshot(event.id)
    data = _event_item(event)
    # 用合并评论后的情感覆盖顶层字段
    merged = sentiment.get("weighted_ratios", {})
    if merged:
        data["sentiment_positive"] = merged.get("positive", data.get("sentiment_positive", 0))
        data["sentiment_negative"] = merged.get("negative", data.get("sentiment_negative", 0))
        data["sentiment_neutral"] = merged.get("neutral", data.get("sentiment_neutral", 0))
    # “报道量趋势”按文章发布时间聚合；热度快照是系统观测时间，不能替代报道日期。
    from collections import OrderedDict

    daily = OrderedDict()
    for a in sorted(articles, key=lambda x: x.publish_time or datetime.min):
        if a.publish_time:
            day = a.publish_time.strftime("%Y-%m-%d")
            daily[day] = daily.get(day, 0) + 1
    if daily:
        trend_dates = list(daily.keys())
        trend_counts = list(daily.values())
        heat_by_day = {
            item.calculated_at.strftime("%Y-%m-%d"): item.final_heat
            for item in snapshots
            if item.calculated_at
        }
        trend_heat = [heat_by_day.get(day) for day in trend_dates]
    elif snapshots:
        trend_dates = [item.calculated_at.isoformat() for item in snapshots]
        trend_counts = [
            (item.raw_statistics or {}).get("independent_report_count_7d", 0)
            for item in snapshots
        ]
        trend_heat = [item.final_heat for item in snapshots]
    else:
        trend_dates = []
        trend_counts = []
        trend_heat = []
    lifecycle_points = get_lifecycle_change_points(trend_counts, trend_dates)
    # 风险摘要：用文章已有字段聚合，不重新调 LLM（已在前置管线中计算并存入 DB）
    suspicious_articles = [a for a in articles if getattr(a, "is_suspicious", False)]
    risk_scores = [float(getattr(a, "suspicious_score", 0) or 0) for a in articles]
    avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0
    risk_data = {
        "score": round(avg_risk, 1),
        "level": "高风险" if avg_risk >= 70 else "中风险" if avg_risk >= 40 else "低风险",
        "suspicious_count": len(suspicious_articles),
        "total_count": len(articles),
        "factors": [],
    }

    # 风险数据：优先 LLM 报告，缺失时用规则回退
    if report and report.risk_data:
        risk_payload = report.risk_data
    else:
        risk_payload = _rule_based_risk(event, articles)
    data.update(
        report={
            "overview_text": report.overview_text if report else event.summary,
            "risk_data": risk_payload,
        },
        trend={
            "dates": [short_date(value) for value in trend_dates[-14:]],
            "counts": trend_counts[-14:],
            "heat": trend_heat,
            "key_points": trend_key_points([short_date(value) for value in trend_dates[-14:]],trend_counts[-14:]),
        },
        sentiment=sentiment,
        public_opinion=public_opinion,
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
        keywords=_merged_keywords(event, public_opinion),
        articles={
            "articles": [
                {
                    "id": article.id,
                    "platform": api_platform_name(article.platform) or "未知平台",
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
    """获取事件溯源与关键传播路径数据。

    优先读缓存（发布时后台计算），缓存未命中则实时计算关键词聚焦图。
    按设计规范返回：1 源头节点 + 5 关键词节点 + 最多 5 条有向边。
    """
    event = Event.query.get(event_id)
    if event is None:
        return None
    cached = (event.metadata_evidence or {}).get("propagation")
    if cached:
        return cached

    # 缓存未命中：实时构建关键词聚焦传播图
    articles = Article.query.filter_by(event_id=event.id)\
        .order_by(Article.publish_time.asc()).all()
    from app.services.propagation_analysis_service import analyze_propagation
    top_keywords = (_event_keywords(event).get("keywords") or [])[:5]
    result = analyze_propagation(
        event.title, articles, {},
        top_keywords=top_keywords,
    )
    result["status"] = "pending" if result.get("origin_analysis", {}).get("status") != "success" else "completed"
    return result


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
