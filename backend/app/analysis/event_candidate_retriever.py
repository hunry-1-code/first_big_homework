from __future__ import annotations

from app.analysis.event_similarity import set_similarity


def rank_candidates(document, candidates, limit: int = 20):
    ranked = []
    for candidate in candidates:
        topic_score = 1.0 if document.topic_category and document.topic_category == candidate.topic_category else 0.0
        keyword_score = set_similarity(document.keywords, candidate.keywords) or 0.0
        ranked.append((topic_score + keyword_score, candidate.cluster_index, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[: max(1, int(limit))]]


__all__ = ["rank_candidates"]
