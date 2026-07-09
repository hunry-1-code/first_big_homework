from app.services.event_service import get_event_detail


def get_report(event_id: int) -> dict:
    detail = get_event_detail(event_id)
    return {
        "event_id": event_id,
        "overview_text": detail["report"]["overview_text"],
        "trend_data": detail["trend"],
        "sentiment_data": detail["sentiment"],
        "platform_data": detail["platform"],
        "keywords_data": detail["keywords"],
        "risk_data": detail["report"]["risk_data"],
    }

