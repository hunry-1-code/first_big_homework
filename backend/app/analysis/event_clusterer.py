from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from app.analysis.aggregation_config import AggregationConfig
from app.analysis.event_candidate_retriever import rank_candidates
from app.analysis.event_similarity import (
    cosine_similarity,
    entity_similarity,
    score_event_match,
)


def _mean_vector(vectors: list[list[float] | tuple[float, ...] | None], normalize=False):
    rows = [[float(value) for value in vector] for vector in vectors if vector is not None]
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        return None
    output = [sum(row[index] for row in rows) / len(rows) for index in range(len(rows[0]))]
    if normalize:
        norm = math.sqrt(sum(value * value for value in output))
        if norm:
            output = [value / norm for value in output]
    return output


def _merge_entities(items: Iterable[dict[str, frozenset[str]]]) -> dict[str, frozenset[str]]:
    output: dict[str, set[str]] = {}
    for item in items:
        for key, values in item.items():
            output.setdefault(key, set()).update(values)
    return {key: frozenset(values) for key, values in output.items()}


@dataclass(slots=True)
class AggregationDocument:
    article_id: int
    title: str
    effective_time: datetime | None
    platform: str
    tfidf_vector: list[float] | None = None
    bge_vector: list[float] | None = None
    keywords: frozenset[str] = frozenset()
    entities: dict[str, frozenset[str]] = field(default_factory=dict)
    topic_category: str | None = None
    topic_name: str | None = None

    @property
    def evidence_count(self) -> int:
        return sum(
            (
                bool(self.tfidf_vector),
                bool(self.bge_vector),
                bool(self.keywords),
                any(self.entities.values()),
            )
        )


@dataclass(slots=True)
class EventCluster:
    cluster_index: int
    documents: list[AggregationDocument]
    formal_event_id: int | None = None
    tfidf_center: list[float] | None = None
    bge_center: list[float] | None = None
    keywords: frozenset[str] = frozenset()
    entities: dict[str, frozenset[str]] = field(default_factory=dict)
    topic_category: str | None = None
    topic_name: str | None = None

    def recompute(self) -> None:
        self.tfidf_center = _mean_vector([item.tfidf_vector for item in self.documents])
        self.bge_center = _mean_vector(
            [item.bge_vector for item in self.documents], normalize=True
        )
        self.keywords = frozenset(
            value for document in self.documents for value in document.keywords
        )
        self.entities = _merge_entities(document.entities for document in self.documents)
        if not self.topic_category:
            self.topic_category = next(
                (item.topic_category for item in self.documents if item.topic_category), None
            )
        if not self.topic_name:
            self.topic_name = next(
                (item.topic_name for item in self.documents if item.topic_name), None
            )


@dataclass(slots=True)
class ClusterAssignment:
    article_id: int
    cluster_index: int | None
    action: str
    similarity: float
    component_scores: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClusterResult:
    clusters: list[EventCluster]
    assignments: list[ClusterAssignment]
    warnings: list[str] = field(default_factory=list)


def _time_compatibility(document: AggregationDocument, cluster: EventCluster, config):
    times = [item.effective_time for item in cluster.documents if item.effective_time]
    if document.effective_time is None or not times:
        return None
    gap_days = min(
        abs((document.effective_time - value).total_seconds()) for value in times
    ) / 86400
    half_life = max(1.0, float(config.maximum_event_gap_days))
    return math.exp(-math.log(2.0) * gap_days / half_life)


def _score(document: AggregationDocument, cluster: EventCluster, config):
    return score_event_match(
        config=config,
        bge_similarity=cosine_similarity(document.bge_vector, cluster.bge_center),
        tfidf_similarity=cosine_similarity(document.tfidf_vector, cluster.tfidf_center),
        entity_similarity=entity_similarity(document.entities, cluster.entities),
        time_compatibility=_time_compatibility(document, cluster, config),
        article_entities=document.entities,
        candidate_entities=cluster.entities,
    )


def cluster_documents(
    documents: Iterable[AggregationDocument], config: AggregationConfig
) -> ClusterResult:
    ordered = sorted(
        documents,
        key=lambda item: (
            item.effective_time is None,
            item.effective_time or datetime.max,
            item.article_id,
        ),
    )
    clusters: list[EventCluster] = []
    assignments: list[ClusterAssignment] = []
    for document in ordered:
        if document.evidence_count < config.minimum_evidence_count:
            assignments.append(
                ClusterAssignment(
                    article_id=document.article_id,
                    cluster_index=None,
                    action="deferred",
                    similarity=0.0,
                    reasons=["INSUFFICIENT_EVIDENCE"],
                )
            )
            continue
        best_cluster = None
        best_score = None
        for candidate in rank_candidates(document, clusters, config.candidate_limit):
            result = _score(document, candidate, config)
            if best_score is None or result.final_score > best_score.final_score:
                best_cluster, best_score = candidate, result
        if (
            best_cluster is not None
            and best_score is not None
            and not best_score.hard_conflict
            and best_score.final_score >= config.attach_threshold
        ):
            best_cluster.documents.append(document)
            best_cluster.recompute()
            assignments.append(
                ClusterAssignment(
                    article_id=document.article_id,
                    cluster_index=best_cluster.cluster_index,
                    action="attach",
                    similarity=best_score.final_score,
                    component_scores=best_score.component_scores,
                    reasons=best_score.reasons,
                    warnings=best_score.warnings,
                )
            )
            continue
        cluster = EventCluster(cluster_index=len(clusters), documents=[document])
        cluster.recompute()
        clusters.append(cluster)
        assignments.append(
            ClusterAssignment(
                article_id=document.article_id,
                cluster_index=cluster.cluster_index,
                action="create",
                similarity=best_score.final_score if best_score else 0.0,
                component_scores=best_score.component_scores if best_score else {},
                reasons=best_score.reasons if best_score else [],
                warnings=best_score.warnings if best_score else [],
            )
        )
    return ClusterResult(clusters=clusters, assignments=assignments)


__all__ = [
    "AggregationDocument",
    "ClusterAssignment",
    "ClusterResult",
    "EventCluster",
    "cluster_documents",
]
