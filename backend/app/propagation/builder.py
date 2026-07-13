from app.propagation.evidence import (
    author_matches,
    explicit_parent_authors,
    explicit_parent_ids,
)
from app.propagation.phases import classify
from app.propagation.scorer import inferred_score


def _time(article):
    return getattr(article, "publish_time", None) or getattr(article, "first_crawled_at", None)


def _interactions(article):
    return sum(
        (getattr(article, field, 0) or 0)
        for field in ("likes_count", "comments_count", "reposts_count", "views_count")
    )


def _time_gap_hours(parent, child):
    if not _time(parent) or not _time(child):
        return None
    return round((_time(child) - _time(parent)).total_seconds() / 3600, 2)


def _explicit_parent(child, earlier, by_source):
    for parent_id in explicit_parent_ids(child):
        parent = by_source.get(parent_id)
        if parent is not None and parent.id != child.id:
            return parent, "平台原始转发或引用关系"
    authors = explicit_parent_authors(child)
    for parent in reversed(earlier):
        if any(author_matches(getattr(parent, "author", ""), value) for value in authors):
            return parent, "正文包含明确转发或来源作者"
    return None, None


def build_propagation_graph(articles, platform_mapper=lambda value: value, max_nodes=40):
    rows = sorted(
        articles,
        key=lambda article: (_time(article) is None, _time(article), article.id),
    )
    by_source = {}
    for article in rows:
        by_source[str(article.id)] = article
        source_article_id = getattr(article, "source_article_id", None)
        if source_article_id is not None:
            by_source[str(source_article_id)] = article

    links = []
    incoming = set()
    for index, child in enumerate(rows):
        earlier = rows[:index]
        explicit, explicit_reason = _explicit_parent(child, earlier, by_source)
        if explicit and (
            _time(explicit) is None
            or _time(child) is None
            or _time(explicit) <= _time(child)
        ):
            links.append(
                {
                    "source": explicit.id,
                    "target": child.id,
                    "relation_type": "repost_or_quote",
                    "evidence_type": "explicit",
                    "confidence": 1.0,
                    "evidence": [explicit_reason],
                    "evidence_components": {"explicit": 1.0},
                    "time_gap_hours": _time_gap_hours(explicit, child),
                }
            )
            incoming.add(child.id)
            continue

        candidates = []
        for parent in earlier:
            evidence = inferred_score(parent, child)
            if evidence.eligible:
                candidates.append((evidence, parent))
        if not candidates:
            continue
        evidence, parent = max(
            candidates,
            key=lambda item: (item[0].final_score, _time(item[1]) or 0),
        )
        links.append(
            {
                "source": parent.id,
                "target": child.id,
                "relation_type": (
                    "cross_platform_followup"
                    if parent.platform != child.platform
                    else "content_followup"
                ),
                "evidence_type": "inferred",
                "confidence": round(evidence.final_score, 3),
                "evidence": list(evidence.reasons),
                "evidence_components": evidence.components(),
                "time_gap_hours": _time_gap_hours(parent, child),
            }
        )
        incoming.add(child.id)

    roots = {article.id for article in rows if article.id not in incoming}
    first_platform = {}
    for article in rows:
        first_platform.setdefault(article.platform, article.id)
    peak = max(rows, key=_interactions).id if rows else None
    nodes = []
    key_nodes = []
    phases = []
    for article in rows[:max_nodes]:
        kind, reasons = classify(
            article,
            article.id in roots,
            first_platform.get(article.platform) == article.id,
            article.id == peak,
        )
        node = {
            "id": article.id,
            "article_id": article.id,
            "name": getattr(article, "author", None) or "匿名用户",
            "title": getattr(article, "title", ""),
            "platform": platform_mapper(article.platform) or article.platform,
            "publish_time": _time(article).isoformat() if _time(article) else None,
            "time_confidence": "high" if getattr(article, "publish_time", None) else "low",
            "node_type": kind,
            "category": kind,
            "interaction_count": _interactions(article),
            "symbolSize": 18 + min(24, _interactions(article) ** 0.25),
            "is_key_node": kind != "ordinary" or bool(reasons),
            "key_node_reasons": reasons,
        }
        nodes.append(node)
        if node["is_key_node"]:
            key_nodes.append(node)
    for node in key_nodes:
        if node["node_type"] in {
            "origin_candidate",
            "influencer_amplification",
            "media_intervention",
            "official_response",
            "peak_content",
        }:
            phases.append(
                {
                    "phase_type": node["node_type"],
                    "time": node["publish_time"],
                    "representative_node_id": node["id"],
                    "title": node["title"],
                }
            )
    ids = {node["id"] for node in nodes}
    links = [link for link in links if link["source"] in ids and link["target"] in ids]
    explicit_count = sum(link["evidence_type"] == "explicit" for link in links)
    inferred_count = sum(link["evidence_type"] == "inferred" for link in links)
    coverage_status = "sufficient" if links else "insufficient"
    limitations = []
    if not nodes:
        limitations.append("当前事件没有可用于传播分析的报道")
    elif not links:
        limitations.append("现有报道之间缺少足够的显式或推断传播证据")
    elif not explicit_count:
        limitations.append("当前传播边均为推断关系，尚无平台原始转发或引用证据")
    return {
        "coverage_status": coverage_status,
        "graph_mode": "propagation",
        "limitations": limitations,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(links),
            "explicit_edge_count": explicit_count,
            "inferred_edge_count": inferred_count,
            "origin_candidate_count": len(roots),
            "platforms": sorted({node["platform"] for node in nodes}),
            "coverage_notice": (
                f"基于已采集的{len(nodes)}篇报道重建传播网络，含{len(links)}条传播路径"
                f"（{explicit_count}条显式、{inferred_count}条推断）"
            ),
        },
        "key_nodes": key_nodes,
        "phases": phases,
        "graph": {"nodes": nodes, "links": links, "secondary_links": []},
    }
