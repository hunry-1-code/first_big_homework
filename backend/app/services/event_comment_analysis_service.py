from __future__ import annotations

from app.extensions import db
from app.models import Event
from app.services.public_opinion_service import (
    analyze_narrative_gap,
    extract_opinion_themes,
    upgrade_comment_sentiments,
)


def analyze_event_comments(event_id: int) -> dict:
    event = db.session.get(Event, int(event_id))
    if event is None:
        raise KeyError(f"event not found: {event_id}")

    result = {
        "sentiment": upgrade_comment_sentiments(event.id),
        "themes": None,
        "narrative_gap": None,
        "warnings": [],
    }
    metadata = dict(event.metadata_evidence or {})

    try:
        themes = extract_opinion_themes(event.id)
        result["themes"] = themes
        if themes:
            metadata["opinion_themes"] = themes
    except Exception as exc:
        result["warnings"].append(f"OPINION_THEMES_FAILED:{type(exc).__name__}")

    try:
        gap = analyze_narrative_gap(event.id)
        result["narrative_gap"] = gap
        if gap:
            metadata["narrative_gap_analysis"] = gap
    except Exception as exc:
        result["warnings"].append(f"NARRATIVE_GAP_FAILED:{type(exc).__name__}")

    event.metadata_evidence = metadata
    db.session.commit()
    return result


__all__ = ["analyze_event_comments"]
