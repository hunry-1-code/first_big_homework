from flask import current_app

from app.llm.client import LLMClient
from app.models import Article, Event


_QA_HISTORY: list[dict] = []


def _event_context(event_id: int) -> str:
    event = Event.query.get(int(event_id))
    if event is None:
        raise KeyError(f"event not found: {event_id}")
    articles = Article.query.filter_by(event_id=event.id).order_by(Article.id).limit(20).all()
    article_lines = [
        f"- [{item.platform}] {item.title or '无标题'}：{(item.clean_content or '')[:300]}"
        for item in articles
    ]
    return "\n".join(
        [
            f"事件标题：{event.title or '未命名事件'}",
            f"事件概述：{event.summary or '暂无概述'}",
            f"生命周期：{event.lifecycle_stage or '未知'}",
            f"情感比例：正面 {float(event.sentiment_positive or 0):.3f}，负面 {float(event.sentiment_negative or 0):.3f}，中立 {float(event.sentiment_neutral or 0):.3f}",
            "相关报道：",
            *(article_lines or ["- 暂无报道正文"]),
        ]
    )


def answer_question(user_id: int, question: str, event_id=None) -> dict:
    context = _event_context(event_id) if event_id is not None else "用户未指定事件，请仅回答一般舆情分析问题。"
    client = LLMClient(
        api_key=current_app.config.get("LLM_API_KEY", ""),
        base_url=current_app.config.get("LLM_BASE_URL", ""),
        model_name=current_app.config.get("LLM_MODEL_NAME", ""),
        timeout=current_app.config.get("LLM_REQUEST_TIMEOUT", 30),
    )
    method = "llm"
    model_name = None
    warnings = []
    try:
        response = client.chat(
            [
                {"role": "system", "content": "你是舆情分析助手。只能依据给定事件材料回答；证据不足时明确说明，不得编造。"},
                {"role": "user", "content": f"以下是事件材料：\n{context}\n\n问题：{question}"},
            ],
            temperature=0.2,
        )
        answer = response["content"]
        model_name = response.get("model")
    except Exception:
        method = "fallback"
        warnings = ["LLM_UNAVAILABLE"]
        if event_id is None:
            answer = "当前大模型服务不可用，暂时无法回答一般性问题。"
        else:
            event = Event.query.get(int(event_id))
            answer = f"当前大模型服务不可用。已检索到事件“{event.title}”，请稍后重试以获得基于报道内容的分析。"
    record = {
        "id": len(_QA_HISTORY) + 1,
        "user_id": user_id,
        "event_id": event_id,
        "question": question,
        "answer": answer,
        "method": method,
        "model_name": model_name,
        "warnings": warnings,
    }
    _QA_HISTORY.append(record)
    return {"qa_id": record["id"], "question": question, "answer": answer, "event_id": event_id, "method": method, "model_name": model_name, "warnings": warnings}


def list_history(user_id: int) -> dict:
    records = [item for item in _QA_HISTORY if item["user_id"] == user_id]
    return {"records": records, "total": len(records)}

