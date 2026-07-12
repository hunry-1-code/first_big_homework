from __future__ import annotations

from app.analysis.aggregation_config import AggregationConfig
from app.analysis.event_similarity import cosine_similarity
from app.analysis.heat_calculator import calculate_event_heats


DEFAULT_EVENT_SIMILARITY_THRESHOLD = AggregationConfig().attach_threshold


def assign_event_cluster(article_vector: dict, event_vectors: list[dict]) -> dict:
    vector = article_vector.get("vector") if isinstance(article_vector, dict) else None
    best_event_id = None
    best_similarity = 0.0
    for candidate in event_vectors:
        similarity = cosine_similarity(vector, candidate.get("vector"))
        if similarity is not None and similarity > best_similarity:
            best_event_id = candidate.get("event_id")
            best_similarity = similarity
    attach = (
        best_event_id is not None
        and best_similarity >= DEFAULT_EVENT_SIMILARITY_THRESHOLD
    )
    return {
        "event_id": best_event_id if attach else None,
        "action": "attach" if attach else "create",
        "similarity": round(best_similarity, 6),
        "threshold": DEFAULT_EVENT_SIMILARITY_THRESHOLD,
    }


__all__ = [
    "DEFAULT_EVENT_SIMILARITY_THRESHOLD",
    "assign_event_cluster",
    "calculate_event_heats",
]
