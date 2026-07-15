from __future__ import annotations


def build_prediction_payload(event) -> dict:
    evidence = dict(event.lifecycle_evidence or {})
    momentum = float(evidence.get("momentum") or 0.0)
    if momentum > 0.1:
        direction = "上升"
    elif momentum < -0.1:
        direction = "下降"
    else:
        direction = "平稳"
    updated = getattr(event, "lifecycle_updated_at", None)
    return {
        "current_stage": event.lifecycle_stage or "未知",
        "confidence": float(event.lifecycle_confidence or 0.0),
        "status": event.lifecycle_status or "data_insufficient",
        "momentum": momentum,
        "next_stage": evidence.get("next_stage_hint"),
        "trend_direction": direction,
        "trend_explanation": evidence.get("trend_explanation", ""),
        "next_stage_reason": evidence.get("next_stage_reason", ""),
        "risks": list(evidence.get("trend_risks") or []),
        "analysis_status": evidence.get("llm_status", "unavailable"),
        "model": evidence.get("llm_model"),
        "generated_at": updated.isoformat() if updated else None,
        "evidence": {
            "total_articles": int(evidence.get("total_articles") or 0),
            "total_comments": int(evidence.get("total_comments") or 0),
            "recent_articles": int(evidence.get("recent_articles_24h") or 0),
            "recent_comments": int(evidence.get("recent_comments_24h") or 0),
            "comment_growing": bool(evidence.get("comment_growing")),
            "sentiment_polarizing": bool(evidence.get("sentiment_polarizing")),
            "dates": list(evidence.get("dates") or []),
        },
    }


__all__ = ["build_prediction_payload"]
