from __future__ import annotations


DEFAULT_EVENT_SIMILARITY_THRESHOLD = 0.5


def assign_event_cluster(article_vector: dict, event_vectors: list[dict]) -> dict:
    return {
        "event_id": None,
        "action": "create",
        "similarity": 0.0,
        "threshold": DEFAULT_EVENT_SIMILARITY_THRESHOLD,
    }
