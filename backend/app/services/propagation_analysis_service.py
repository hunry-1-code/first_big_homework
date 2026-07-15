from __future__ import annotations

from collections import Counter
import json
import re

from app.llm.doubao_client import DoubaoClient, DoubaoUnavailableError
from app.propagation.evidence import keyword_or_entity_terms
from app.propagation.keyword_relations import build_keyword_relations


def _doubao_from_config():
    from flask import current_app

    return DoubaoClient(
        api_key=current_app.config.get("DOUBAO_ARK_API_KEY", ""),
        base_url=current_app.config.get("DOUBAO_ARK_BASE_URL", ""),
        model_name=current_app.config.get("DOUBAO_ARK_MODEL", ""),
        timeout=current_app.config.get("DOUBAO_REQUEST_TIMEOUT", 60),
    )


def _top_five_keywords(articles, supplied) -> list[dict]:
    normalized = []
    seen = set()
    for item in supplied or []:
        word = str((item or {}).get("word") or (item or {}).get("term") or "").strip()
        if not word or word in seen:
            continue
        seen.add(word)
        normalized.append(
            {
                "word": word,
                "weight": float((item or {}).get("weight") or (item or {}).get("score") or 0),
            }
        )
    normalized.sort(key=lambda item: (-item["weight"], item["word"]))
    if normalized:
        return normalized[:5]

    counts = Counter()
    for article in articles:
        counts.update(
            str(term).strip()
            for term in keyword_or_entity_terms(article)
            if 2 <= len(str(term).strip()) <= 30
        )
    return [
        {"word": word, "weight": float(count)}
        for word, count in counts.most_common(5)
    ]


def _parse_json_object(text: str) -> dict:
    value = str(text or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, re.I | re.S)
    if fenced:
        value = fenced.group(1).strip()
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, re.S)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("豆包溯源结果必须是 JSON 对象")
    return payload


def _validated_trace(payload: dict, keywords: list[dict], citations: list[dict]) -> dict:
    valid_terms = {item["word"] for item in keywords}
    citation_urls = {str(item.get("url") or "") for item in citations if item.get("url")}
    origin = payload.get("origin") if isinstance(payload.get("origin"), dict) else None
    if origin:
        url = str(origin.get("url") or "").strip()
        if not url and citations:
            url = str(citations[0].get("url") or "")
        origin = {
            "title": str(origin.get("title") or "疑似最早公开来源")[:200],
            "url": url,
            "publish_time": str(origin.get("publish_time") or "")[:80] or None,
            "source": str(origin.get("source") or "互联网公开来源")[:100],
            "reason": str(origin.get("reason") or "豆包联网搜索候选")[:500],
            "confidence": min(1.0, max(0.0, float(origin.get("confidence") or 0.5))),
        }
    paths = []
    for item in payload.get("paths") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if source not in valid_terms or target not in valid_terms or source == target:
            continue
        evidence_urls = [
            str(url) for url in (item.get("evidence_urls") or [])
            if str(url) in citation_urls
        ]
        paths.append(
            {
                "source": source,
                "target": target,
                "reason": str(item.get("reason") or "关键词传播关联")[:500],
                "confidence": min(1.0, max(0.0, float(item.get("confidence") or 0.6))),
                "evidence_urls": evidence_urls[:3],
            }
        )
    return {
        "summary": str(payload.get("summary") or "")[:1200],
        "origin": origin,
        "paths": paths[:8],
    }


def _keyword_nodes(keywords: list[dict]) -> list[dict]:
    maximum = max((item["weight"] for item in keywords), default=1.0) or 1.0
    return [
        {
            "id": f"keyword:{index}",
            "name": item["word"],
            "title": f"高频词：{item['word']}（权重 {item['weight']:.4g}）",
            "platform": "事件词云",
            "publish_time": None,
            "time_confidence": "derived",
            "node_type": "ordinary",
            "category": "ordinary",
            "interaction_count": item["weight"],
            "symbolSize": round(24 + 16 * item["weight"] / maximum, 2),
            "is_key_node": True,
            "key_node_reasons": ["事件词云频率 Top 5"],
            "keyword": item["word"],
            "frequency_weight": item["weight"],
        }
        for index, item in enumerate(keywords)
    ]


def _rule_keyword_links(nodes: list[dict], existing_pairs=None) -> list[dict]:
    existing_pairs = set(existing_pairs or [])
    output = []
    for source, target in zip(nodes, nodes[1:]):
        pair = (source["keyword"], target["keyword"])
        if pair in existing_pairs:
            continue
        output.append(
            {
                "source": source["id"],
                "target": target["id"],
                "relation_type": "keyword_evolution",
                "evidence_type": "keyword_frequency_rule",
                "confidence": 0.55,
                "evidence": ["按词云频率顺序和事件内共同出现关系生成的基础路径"],
                "evidence_urls": [],
            }
        )
    return output


def _focused_graph(keywords: list[dict], trace: dict | None) -> dict:
    keyword_nodes = _keyword_nodes(keywords)
    nodes = list(keyword_nodes)
    links = []
    by_word = {node["keyword"]: node for node in keyword_nodes}

    origin = (trace or {}).get("origin")
    if origin:
        origin_node = {
            "id": "internet:origin",
            "name": origin["source"] or "疑似源头",
            "title": origin["title"],
            "platform": origin["source"],
            "publish_time": origin["publish_time"],
            "time_confidence": "web_search",
            "node_type": "origin_candidate",
            "category": "origin_candidate",
            "interaction_count": 0,
            "symbolSize": 44,
            "is_key_node": True,
            "key_node_reasons": [origin["reason"]],
            "source_url": origin["url"],
        }
        nodes.insert(0, origin_node)
        if keyword_nodes:
            links.append(
                {
                    "source": origin_node["id"],
                    "target": keyword_nodes[0]["id"],
                    "relation_type": "origin_to_topic",
                    "evidence_type": "doubao_web_search",
                    "confidence": origin["confidence"],
                    "evidence": [origin["reason"]],
                    "evidence_urls": [origin["url"]] if origin["url"] else [],
                }
            )

    path_by_pair = {
        (path["source"], path["target"]): path
        for path in (trace or {}).get("paths") or []
    }
    for source, target in zip(keyword_nodes, keyword_nodes[1:]):
        path = path_by_pair.get((source["keyword"], target["keyword"]))
        if path:
            links.append(
                {
                    "source": source["id"],
                    "target": target["id"],
                    "relation_type": "keyword_evolution",
                    "evidence_type": "doubao_web_search",
                    "confidence": path["confidence"],
                    "evidence": [path["reason"]],
                    "evidence_urls": path["evidence_urls"],
                }
            )
        else:
            links.extend(_rule_keyword_links([source, target]))
    return {"nodes": nodes[:6], "links": links, "secondary_links": []}


def analyze_propagation(
    event_title: str,
    articles,
    graph: dict,
    *,
    doubao_client=None,
    top_keywords=None,
    client=None,
) -> dict:
    articles = list(articles)
    keywords = _top_five_keywords(articles, top_keywords)
    keyword_relations = build_keyword_relations(articles, limit=10)
    selected_client = doubao_client or (client if hasattr(client, "web_search") else None)
    origin_analysis = {
        "status": "unavailable",
        "method": "doubao_web_search",
        "scope": "internet_web_search",
        "origin": None,
        "citations": [],
        "limitations": [],
    }
    trace = None
    model = None
    summary = ""
    error = None

    if keywords:
        query = (
            f"请对事件《{event_title}》进行全互联网溯源。重点检索最早公开来源，并分析以下词云高频词的传播联系："
            f"{', '.join(item['word'] for item in keywords)}。"
            "只输出JSON对象，格式为："
            '{"summary":"溯源概述","origin":{"title":"疑似最早来源标题","url":"原始URL",'
            '"publish_time":"发布时间","source":"来源名称","reason":"判断理由","confidence":0.8},'
            '"paths":[{"source":"必须是给定关键词","target":"必须是给定关键词",'
            '"reason":"传播联系","confidence":0.8,"evidence_urls":["检索到的URL"]}]}。'
            "不得把无法确认的来源表述为绝对首发。"
        )
        try:
            selected_client = selected_client or _doubao_from_config()
            response = selected_client.web_search(query, limit=10)
            model = response.get("model") or getattr(selected_client, "model_name", None)
            citations = response.get("citations") or []
            search_text = str(response.get("text") or "").strip()
            try:
                payload = _parse_json_object(search_text)
                trace = _validated_trace(payload, keywords, citations)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                if not citations:
                    raise
                first = citations[0]
                trace = {
                    "summary": search_text[:1200],
                    "origin": {
                        "title": str(first.get("title") or "豆包联网检索候选来源")[:200],
                        "url": str(first.get("url") or ""),
                        "publish_time": None,
                        "source": "豆包联网搜索引用",
                        "reason": "豆包已完成联网检索，但结构化JSON解析失败；暂以首条引用作为待核验候选来源。",
                        "confidence": 0.5,
                    },
                    "paths": [],
                }
                origin_analysis["limitations"].append(
                    f"豆包结构化结果解析失败({type(exc).__name__})，已保留联网引用并降级构图"
                )
            summary = trace["summary"]
            origin_analysis.update(
                status="success" if trace.get("origin") else "partial",
                origin=trace.get("origin"),
                citations=citations[:10],
            )
            if not trace.get("origin"):
                origin_analysis["limitations"].append("豆包返回了搜索结果，但未确认疑似最早来源")
        except DoubaoUnavailableError as exc:
            error = str(exc)[:500]
            origin_analysis["limitations"].append("豆包联网搜索不可用，未生成全网源头节点")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            error = str(exc)[:500]
            origin_analysis["status"] = "invalid"
            origin_analysis["limitations"].append("豆包联网结果无法解析为结构化溯源证据")
        except Exception as exc:
            error = str(exc)[:500]
            origin_analysis["limitations"].append("豆包联网搜索调用失败")

    focused = _focused_graph(keywords, trace)

    # 用 DeepSeek 解释每个关键词为何高频 + 关键词间演化关系
    keyword_explanations = _explain_keyword_evolution(
        event_title, keywords, keyword_relations, focused["links"], focused["nodes"]
    )
    if not keyword_explanations:
        keyword_explanations = [
            {"terms": [link.get("source"), link.get("target")], "reason": link["evidence"][0]}
            for link in focused["links"]
        ]

    link_types = Counter(link["evidence_type"] for link in focused["links"])
    trace_succeeded = origin_analysis["status"] == "success" and bool(
        origin_analysis.get("origin")
    )
    result = {
        "coverage_status": "sufficient" if trace_succeeded and focused["links"] else "insufficient",
        "graph_mode": "focused_keyword_path",
        "requires_doubao_trace": True,
        "trace_completed": trace_succeeded,
        "limitations": origin_analysis["limitations"],
        "summary": {
            "node_count": len(focused["nodes"]),
            "edge_count": len(focused["links"]),
            "explicit_edge_count": link_types["doubao_web_search"],
            "inferred_edge_count": link_types["keyword_frequency_rule"],
            "origin_candidate_count": 1 if trace and trace.get("origin") else 0,
            "platforms": sorted({node["platform"] for node in focused["nodes"] if node.get("platform")}),
            "coverage_notice": f"豆包全网溯源与词云Top {len(keywords)}共同构造{len(focused['nodes'])}个节点、{len(focused['links'])}条有向路径",
        },
        "key_nodes": focused["nodes"],
        "phases": [],
        "graph": focused,
        "origin_analysis": origin_analysis,
        "top_keywords": keywords,
        "keyword_relations": keyword_relations,
        "llm_analysis": {
            "status": origin_analysis["status"],
            "model": model,
            "summary": summary,
            "key_paths": focused["links"],
            "keyword_explanations": keyword_explanations,
            "scope": "internet_web_search",
            "error": error,
        },
    }
    return result


def _explain_keyword_evolution(
    event_title: str,
    keywords: list[dict],
    cooccurrence: list[dict],
    links: list[dict],
    nodes: list[dict],
) -> list[dict]:
    """用 DeepSeek 解释关键词高频原因和演化关系。

    输入: 事件标题 + Top5关键词 + 共现数据 + 传播边
    输出: 每个关键词的1句解释 + 每个边对的1句演化理由
    """
    if not keywords or not event_title:
        return []

    # 构造关键词摘要
    kw_lines = []
    for kw in keywords:
        word = kw["word"]
        # 找共现数据
        related = [r for r in cooccurrence if word in (r.get("terms") or [])]
        total_arts = sum(r["article_count"] for r in related[:3]) if related else 0
        total_plats = len(set(p for r in related[:5] for p in r.get("platforms", []))) if related else 0
        kw_lines.append(f"- {word}(权重{kw['weight']:.2f}): 共现{total_arts}篇文章/{total_plats}个平台")

    # 构造边摘要
    edge_lines = []
    id_to_name = {n["id"]: n.get("name", "?") for n in nodes}
    for link in links:
        src = id_to_name.get(link["source"], link["source"])
        tgt = id_to_name.get(link["target"], link["target"])
        etype = "豆包联网证据" if link.get("evidence_type") == "doubao_web_search" else "词频规则"
        edge_lines.append(f"- {src} → {tgt} ({etype}, 置信度{link.get('confidence',0):.0%})")

    prompt = (
        f"事件：{event_title}\n\n"
        f"词云高频词：\n" + "\n".join(kw_lines) + "\n\n"
        f"传播路径：\n" + "\n".join(edge_lines) + "\n\n"
        "请用中文解释：\n"
        "1. 每个关键词：结合事件背景和共现数据，说明该词在事件中的角色和重要原因（40-80字）\n"
        "2. 每条传播路径：解释这两个关键词之间的事件演化关系，即前一个词如何引出/推动后一个词（20-40字）\n\n"
        "返回JSON数组: [{\"type\":\"keyword|edge\",\"target\":\"词名或src→tgt\",\"reason\":\"解释\"}]"
    )

    try:
        from app.llm.client import LLMClient
        from flask import current_app
        client = LLMClient(
            api_key=current_app.config.get("LLM_API_KEY", ""),
            base_url=current_app.config.get("LLM_BASE_URL", ""),
            model_name=current_app.config.get("LLM_MODEL_NAME", "deepseek-chat"),
            timeout=15,
        )
        resp = client.chat([
            {"role": "system", "content": "你是舆情分析师。只返回JSON数组，不要加解释文字。"},
            {"role": "user", "content": prompt}
        ], temperature=0.3, max_tokens=300)

        import re as _re
        text = resp["content"].strip()
        # 去掉 markdown 代码块
        fenced = _re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, _re.DOTALL | _re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        # 提取 JSON 数组
        match = _re.search(r"\[.*\]", text, _re.DOTALL)
        if match:
            text = match.group(0)
        data = json.loads(text)
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception as e:
        pass
    return []


__all__ = ["analyze_propagation"]
