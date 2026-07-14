"""智能问答服务 — DB 持久化 + 多轮对话 + 丰富事件上下文"""
from flask import current_app, g

from app.extensions import db
from app.llm.client import LLMClient
from app.models import Article, Event, QaHistory


def _event_context(event_id: int, platform: str | None = None) -> str:
    """构建丰富的 LLM 事件上下文，包含关键词/情感/AI报告/平台过滤。"""
    event = db.session.get(Event, int(event_id))
    if event is None:
        raise KeyError(f"event not found: {event_id}")

    # 文章列表（平台过滤）
    query = Article.query.filter_by(event_id=event.id)
    if platform:
        query = query.filter_by(platform=platform)
    articles = query.order_by(Article.id).limit(20).all()

    # 关键词（从 event_service 复用）
    kw_lines = ""
    try:
        from app.services.event_service import _event_keywords
        ek = _event_keywords(event)
        kws = ek.get("keywords", [])[:10]
        if kws:
            kw_lines = "关键词: " + ", ".join(
                f"{k['word']}({k.get('sentiment','?')})" for k in kws
            ) + "\n"
    except Exception:
        pass

    article_lines = []
    for item in articles:
        kw_tags = ""
        if hasattr(item, 'sentiment_label') and item.sentiment_label:
            kw_tags = f" [{item.sentiment_label}]"
        article_lines.append(
            f"- [{item.platform}]{kw_tags} {item.title or '无标题'}：{(item.clean_content or '')[:400]}"
        )

    return "\n".join([
        f"事件标题：{event.title or '未命名事件'}",
        f"事件摘要：{event.summary or '暂无'}",
        f"生命周期：{event.lifecycle_stage or '未知'} | 热度：{event.heat_index or 0:.0f}",
        f"情感分布：正面 {float(event.sentiment_positive or 0)*100:.0f}% / 中立 {float(event.sentiment_neutral or 0)*100:.0f}% / 负面 {float(event.sentiment_negative or 0)*100:.0f}%",
        kw_lines,
        f"相关报道（{len(articles)}篇）：",
        *article_lines,
    ])


def _chat_history(user_id: int, limit: int = 6) -> list[dict]:
    """获取用户最近 N 轮对话历史。"""
    rows = (
        QaHistory.query
        .filter_by(user_id=user_id)
        .order_by(QaHistory.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {"role": "user", "content": row.question} if i % 2 == 0
        else {"role": "assistant", "content": row.answer or ""}
        for i, row in enumerate(reversed(rows))
    ]


def answer_question(user_id: int, question: str, event_id=None, platform: str | None = None) -> dict:
    """回答用户问题，支持事件上下文和多轮对话历史。"""
    context = _event_context(event_id, platform) if event_id is not None else "用户未指定事件，请仅回答一般舆情分析问题。"
    history = _chat_history(user_id, 6)  # 最近 3 轮

    client = LLMClient(
        api_key=current_app.config.get("LLM_API_KEY", ""),
        base_url=current_app.config.get("LLM_BASE_URL", ""),
        model_name=current_app.config.get("LLM_MODEL_NAME", ""),
        timeout=current_app.config.get("LLM_REQUEST_TIMEOUT", 30),
    )

    has_event = event_id is not None
    system_prompt = (
        "你是舆情分析助手。"
        + ("只能依据给定事件材料回答；证据不足时明确说明，不得编造。" if has_event
           else "可以结合联网搜索结果回答一般性问题。")
        + "回答应包含：1) 核心结论 2) 支撑数据（如有）3) 信息不足时的说明。"
    )

    method = "llm"
    warnings = []
    model_name = None
    try:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": f"事件材料：\n{context}\n\n问题：{question}"})
        # 无事件时启用联网搜索
        chat_kwargs = {"temperature": 0.2}
        if not has_event:
            chat_kwargs["enable_search"] = True
        response = client.chat(messages, **chat_kwargs)
        answer = response["content"]
        model_name = response.get("model")
    except Exception:
        method = "fallback"
        warnings = ["LLM_UNAVAILABLE"]
        if event_id is not None:
            event = db.session.get(Event, int(event_id))
            answer = f"当前大模型服务不可用。已检索到事件「{event.title}」，包含 {Article.query.filter_by(event_id=event.id).count()} 篇报道，请稍后重试。"
        else:
            answer = "当前大模型服务不可用，暂时无法回答。请稍后重试。"

    # 持久化
    record = QaHistory(
        user_id=user_id,
        event_id=int(event_id) if event_id else None,
        question=question,
        answer=answer,
    )
    db.session.add(record)
    db.session.commit()

    return {
        "qa_id": record.id,
        "question": question,
        "answer": answer,
        "event_id": event_id,
        "method": method,
        "model_name": model_name,
        "warnings": warnings,
    }


def list_history(user_id: int) -> dict:
    """获取用户问答历史（DB 持久化）。"""
    rows = (
        QaHistory.query
        .filter_by(user_id=user_id)
        .order_by(QaHistory.id.desc())
        .limit(50)
        .all()
    )
    records = [
        {
            "id": r.id,
            "event_id": r.event_id,
            "question": r.question,
            "answer": r.answer,
            "created_at": r.created_at.isoformat(timespec="seconds") + "Z" if r.created_at else None,
        }
        for r in rows
    ]
    return {"records": records, "total": len(records)}
