from flask import current_app

from app.services.event_service import get_event_detail, get_propagation_data


def get_report(event_id: int) -> dict | None:
    detail = get_event_detail(event_id)
    if detail is None:
        return None
    propagation = get_propagation_data(event_id)
    return {
        "event_id": event_id,
        "title": detail.get("title", ""),
        "time_code": detail.get("time_code", ""),
        "location": detail.get("location", ""),
        "key_figures": detail.get("key_figures", ""),
        "cause": detail.get("cause", ""),
        "overview_text": detail["report"]["overview_text"],
        "trend_data": detail["trend"],
        "sentiment_data": detail["sentiment"],
        "platform_data": detail["platform"],
        "keywords_data": detail["keywords"],
        "risk_data": detail["report"]["risk_data"],
        "lifecycle_stage": detail.get("lifecycle_stage", ""),
        "heat_index": detail.get("heat_index", 0),
        "article_count": detail.get("articles", {}).get("total", 0),
        "articles": detail.get("articles", {}).get("articles", []),
        "public_opinion": detail.get("public_opinion", {}),
        "prediction": detail.get("prediction", {}),
        "sentiment_positive": detail.get("sentiment_positive", 0),
        "sentiment_negative": detail.get("sentiment_negative", 0),
        "sentiment_neutral": detail.get("sentiment_neutral", 0),
        "propagation": propagation,
    }

