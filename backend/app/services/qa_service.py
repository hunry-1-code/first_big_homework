_QA_HISTORY: list[dict] = []


def answer_question(user_id: int, question: str, event_id=None) -> dict:
    answer = "这是智能问答接口占位回答。后续接入 LLM 和事件上下文检索。"
    record = {
        "id": len(_QA_HISTORY) + 1,
        "user_id": user_id,
        "event_id": event_id,
        "question": question,
        "answer": answer,
    }
    _QA_HISTORY.append(record)
    return {"qa_id": record["id"], "question": question, "answer": answer, "event_id": event_id}


def list_history(user_id: int) -> dict:
    records = [item for item in _QA_HISTORY if item["user_id"] == user_id]
    return {"records": records, "total": len(records)}

