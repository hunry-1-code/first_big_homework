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
    keyword_overlap_score,
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
        keyword_overlap=keyword_overlap_score(document.keywords, cluster.keywords),
        article_entities=document.entities,
        candidate_entities=cluster.entities,
    )


def _best_match(document: AggregationDocument, clusters, config):
    best_cluster = None
    best_score = None
    for candidate in rank_candidates(document, clusters, config.candidate_limit):
        result = _score(document, candidate, config)
        if best_score is None or result.final_score > best_score.final_score:
            best_cluster, best_score = candidate, result
        elif (
            result.final_score == best_score.final_score
            and best_cluster is not None
            and candidate.cluster_index < best_cluster.cluster_index
        ):
            best_cluster, best_score = candidate, result
    return best_cluster, best_score


def _create_cluster(document: AggregationDocument, clusters) -> EventCluster:
    cluster = EventCluster(cluster_index=len(clusters), documents=[document])
    cluster.recompute()
    clusters.append(cluster)
    return cluster


def _apply_assignment(assignment, cluster, action, score) -> None:
    assignment.cluster_index = cluster.cluster_index
    assignment.action = action
    assignment.similarity = score.final_score if score else 0.0
    assignment.component_scores = score.component_scores if score else {}
    assignment.reasons = score.reasons if score else []
    assignment.warnings = score.warnings if score else []


def _recompute_and_renumber(clusters, assignments) -> None:
    clusters.sort(
        key=lambda cluster: (
            min(
                (
                    item.effective_time is None,
                    item.effective_time or datetime.max,
                    item.article_id,
                )
                for item in cluster.documents
            ),
            min(item.article_id for item in cluster.documents),
        )
    )
    assignment_by_article = {item.article_id: item for item in assignments}
    for cluster_index, cluster in enumerate(clusters):
        cluster.cluster_index = cluster_index
        cluster.documents.sort(
            key=lambda item: (
                item.effective_time is None,
                item.effective_time or datetime.max,
                item.article_id,
            )
        )
        cluster.recompute()
        for document in cluster.documents:
            assignment_by_article[document.article_id].cluster_index = cluster_index


def _refine_assignments(documents, clusters, assignments, config) -> None:
    document_by_id = {item.article_id: item for item in documents}
    for assignment in assignments:
        if assignment.action != "ambiguous":
            continue
        document = document_by_id[assignment.article_id]
        best_cluster, best_score = _best_match(document, clusters, config)
        if (
            best_cluster is not None
            and best_score is not None
            and not best_score.hard_conflict
            and best_score.final_score >= config.attach_threshold
        ):
            best_cluster.documents.append(document)
            best_cluster.recompute()
            _apply_assignment(assignment, best_cluster, "attach", best_score)
            continue

        cluster = _create_cluster(document, clusters)
        _apply_assignment(assignment, cluster, "create", best_score)
        if best_score is not None and not best_score.hard_conflict:
            assignment.reasons = [*assignment.reasons, "AMBIGUOUS_AFTER_REFINEMENT"]

    for assignment in assignments:
        if assignment.action != "attach":
            continue
        document = document_by_id[assignment.article_id]
        current_cluster = next(
            (
                cluster
                for cluster in clusters
                if any(item.article_id == document.article_id for item in cluster.documents)
            ),
            None,
        )
        if current_cluster is None or len(current_cluster.documents) <= 1:
            continue
        current_members = [
            item
            for item in current_cluster.documents
            if item.article_id != document.article_id
        ]
        current_without_document = EventCluster(
            cluster_index=current_cluster.cluster_index,
            documents=current_members,
            formal_event_id=current_cluster.formal_event_id,
        )
        current_without_document.recompute()
        current_score = _score(document, current_without_document, config)
        other_clusters = [cluster for cluster in clusters if cluster is not current_cluster]
        best_cluster, best_score = _best_match(document, other_clusters, config)
        if (
            best_cluster is None
            or best_score is None
            or best_score.hard_conflict
            or best_score.final_score < config.attach_threshold
            or best_score.final_score - current_score.final_score < config.move_margin
        ):
            continue
        current_cluster.documents = current_members
        current_cluster.recompute()
        best_cluster.documents.append(document)
        best_cluster.recompute()
        _apply_assignment(assignment, best_cluster, "moved", best_score)
        assignment.reasons = [*assignment.reasons, "MOVE_MARGIN_MET"]

    _recompute_and_renumber(clusters, assignments)


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
        best_cluster, best_score = _best_match(document, clusters, config)
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
        if (
            best_cluster is not None
            and best_score is not None
            and not best_score.hard_conflict
            and best_score.final_score >= config.create_threshold
        ):
            assignments.append(
                ClusterAssignment(
                    article_id=document.article_id,
                    cluster_index=None,
                    action="ambiguous",
                    similarity=best_score.final_score,
                    component_scores=best_score.component_scores,
                    reasons=best_score.reasons,
                    warnings=best_score.warnings,
                )
            )
            continue
        cluster = _create_cluster(document, clusters)
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
    _refine_assignments(ordered, clusters, assignments, config)
    return ClusterResult(clusters=clusters, assignments=assignments)


def cluster_documents_hdbscan(
    documents: Iterable[AggregationDocument],
    config: AggregationConfig,
) -> ClusterResult:
    """HDBSCAN 密度聚类：自动识别噪声点，不需预设簇数。

    与贪心聚类的区别：
    - 贪心: 按时间排序逐篇决定 attach/create/ambiguous，阈值敏感
    - HDBSCAN: 密度估计 + 层次聚类，自动识别噪声，阈值不敏感

    降级策略：HDBSCAN 不可用或结果过差时回退到贪心聚类。
    """
    docs = list(documents)
    if len(docs) < 3:
        return cluster_documents(docs, config)

    try:
        import numpy as np
        from hdbscan import HDBSCAN
        from sklearn.preprocessing import StandardScaler

        # 提取 BGE + TF-IDF 向量拼接
        vectors = []
        for d in docs:
            vec = []
            bge = [float(v) for v in (d.bge_vector or [])]
            tfidf = [float(v) for v in (d.tfidf_vector or [])]
            if not bge and not tfidf:
                vec = [0.0] * 512  # fallback
            else:
                # BGE + TF-IDF 拼接，BGE 权重更高
                if bge:
                    vec.extend(bge)
                if tfidf:
                    pad_len = max(0, len(bge) - len(tfidf)) if bge else 0
                    vec.extend(tfidf + [0.0] * pad_len)
            vectors.append(vec)

        X = np.array(vectors, dtype=np.float64)
        # 标准化
        X = StandardScaler().fit_transform(X)

        # HDBSCAN 参数
        min_size = max(2, config.minimum_evidence_count)
        min_samples = max(1, min_size // 2)

        clusterer = HDBSCAN(
            min_cluster_size=min_size,
            min_samples=min_samples,
            metric="euclidean",
            cluster_selection_method="eom",  # Excess of Mass: better noise handling
            allow_single_cluster=True,
        )
        labels = clusterer.fit_predict(X)

        # 构建聚类结果
        unique_labels = set(labels)
        n_clusters = len(unique_labels - {-1})
        n_noise = int(sum(1 for l in labels if l == -1))

        # 如果 HDBSCAN 把所有点都归为噪声，回退贪心
        if n_clusters == 0:
            return cluster_documents(docs, config)

        clusters: list[EventCluster] = []
        assignments: list[ClusterAssignment] = []

        for label in sorted(unique_labels):
            if label == -1:
                continue  # 噪声点后续处理
            cluster_docs = [docs[i] for i in range(len(docs)) if labels[i] == label]
            cluster = EventCluster(cluster_index=len(clusters), documents=cluster_docs)
            cluster.recompute()
            clusters.append(cluster)

        # 分配文章
        for i, d in enumerate(docs):
            label = labels[i]
            if label == -1:
                # 噪声点：尝试软分配到最近的簇
                best_cluster, best_score = _best_match(d, clusters, config)
                if best_cluster is not None and best_score is not None and best_score.final_score >= config.create_threshold - 0.05:
                    best_cluster.documents.append(d)
                    best_cluster.recompute()
                    assignments.append(ClusterAssignment(
                        article_id=d.article_id, cluster_index=best_cluster.cluster_index,
                        action="soft_attach", similarity=best_score.final_score,
                        reasons=["HDBSCAN_NOISE_SOFT_ATTACH"],
                    ))
                else:
                    assignments.append(ClusterAssignment(
                        article_id=d.article_id, cluster_index=None,
                        action="deferred", similarity=0.0,
                        reasons=["HDBSCAN_NOISE"],
                    ))
            else:
                cluster = clusters[label if label >= 0 else 0]
                assignments.append(ClusterAssignment(
                    article_id=d.article_id, cluster_index=cluster.cluster_index,
                    action="attach", similarity=1.0,
                    reasons=["HDBSCAN_CLUSTER"],
                ))

        _recompute_and_renumber(clusters, assignments)
        warnings = [f"HDBSCAN: {n_clusters} clusters, {n_noise} noise points"]
        return ClusterResult(clusters=clusters, assignments=assignments, warnings=warnings)

    except ImportError:
        return cluster_documents(docs, config)


__all__ = [
    "AggregationDocument",
    "ClusterAssignment",
    "ClusterResult",
    "EventCluster",
    "cluster_documents",
    "cluster_documents_hdbscan",
]
