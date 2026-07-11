from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
from sklearn.decomposition import LatentDirichletAllocation

from app.analysis.hotspot_config import HotspotConfig
from app.analysis.result import AnalysisDocument, EmptyVocabularyError, NoValidDocumentError


@dataclass(slots=True)
class TopicCandidateMetrics:
    topic_count: int
    perplexity: float
    topic_diversity: float
    small_topic_ratio: float
    passed_quality: bool

    def as_dict(self) -> dict:
        return {
            "topic_count": self.topic_count,
            "perplexity": self.perplexity,
            "topic_diversity": self.topic_diversity,
            "small_topic_ratio": self.small_topic_ratio,
            "passed_quality": self.passed_quality,
        }


@dataclass(slots=True)
class DiscoveredTopic:
    topic_index: int
    keywords: list[dict[str, Any]]
    document_count: int
    probability_mass: float

    def as_dict(self) -> dict:
        return {
            "topic_index": self.topic_index,
            "keywords": self.keywords,
            "document_count": self.document_count,
            "probability_mass": self.probability_mass,
        }


@dataclass(slots=True)
class ArticleTopicAssignment:
    article_id: int
    topic_index: int
    probability: float
    probabilities: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "article_id": self.article_id,
            "topic_index": self.topic_index,
            "probability": self.probability,
            "probabilities": self.probabilities,
            "warnings": self.warnings,
        }


@dataclass(slots=True)
class TopicDiscoveryResult:
    method: str
    selected_k: int
    topics: list[DiscoveredTopic]
    assignments: list[ArticleTopicAssignment]
    candidates: list[TopicCandidateMetrics] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def candidate_topic_counts(document_count: int, maximum_topics: int = 12) -> list[int]:
    if document_count < 5:
        return []
    if document_count < 10:
        return [2]
    if document_count < 30:
        return [value for value in (2, 3, 4) if value <= maximum_topics]
    if document_count < 100:
        return [value for value in range(3, min(8, maximum_topics) + 1)]
    upper = min(maximum_topics, max(5, round(math.sqrt(document_count))))
    return list(range(5, upper + 1))


def _keyword_fallback(
    documents: Sequence[AnalysisDocument], config: HotspotConfig
) -> TopicDiscoveryResult:
    counts = Counter(
        token
        for document in documents
        for token in [*document.title_tokens, *document.body_tokens]
        if isinstance(token, str) and token.strip()
    )
    maximum = max(counts.values(), default=1)
    keywords = [
        {
            "term": term,
            "weight": round(count / maximum, 6),
            "rank": rank,
        }
        for rank, (term, count) in enumerate(
            sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
                : config.top_words
            ],
            start=1,
        )
    ]
    return TopicDiscoveryResult(
        method="keyword_topic_fallback",
        selected_k=1,
        topics=[
            DiscoveredTopic(
                topic_index=0,
                keywords=keywords,
                document_count=len(documents),
                probability_mass=float(len(documents)),
            )
        ],
        assignments=[
            ArticleTopicAssignment(
                article_id=document.article_id,
                topic_index=0,
                probability=1.0,
                probabilities=[{"topic_index": 0, "probability": 1.0}],
            )
            for document in documents
        ],
        warnings=["KEYWORD_TOPIC_FALLBACK"],
    )


def _topic_metrics(
    model: LatentDirichletAllocation,
    distribution,
    count_matrix,
    top_word_count: int,
    config: HotspotConfig,
) -> TopicCandidateMetrics:
    primary = np.asarray(distribution).argmax(axis=1)
    counts = np.bincount(primary, minlength=model.n_components)
    small_threshold = max(2, math.ceil(distribution.shape[0] * 0.03))
    small_topic_ratio = float(np.mean(counts < small_threshold))
    top_indexes = [
        component.argsort()[::-1][:top_word_count].tolist()
        for component in model.components_
    ]
    unique_terms = len({index for indexes in top_indexes for index in indexes})
    denominator = max(1, model.n_components * top_word_count)
    topic_diversity = unique_terms / denominator
    perplexity = float(model.perplexity(count_matrix))
    return TopicCandidateMetrics(
        topic_count=model.n_components,
        perplexity=perplexity,
        topic_diversity=topic_diversity,
        small_topic_ratio=small_topic_ratio,
        passed_quality=(
            topic_diversity >= config.topic_diversity_min
            and small_topic_ratio <= config.small_topic_ratio_max
        ),
    )


def _select_candidate(candidates):
    eligible = [item for item in candidates if item[2].passed_quality]
    warnings: list[str] = []
    pool = eligible or candidates
    if not eligible:
        warnings.append("TOPIC_QUALITY_DEGRADED")
    best_perplexity = min(item[2].perplexity for item in pool)
    close = [
        item
        for item in pool
        if item[2].perplexity <= best_perplexity * 1.02
    ]
    return min(close, key=lambda item: item[2].topic_count), warnings


def discover_topics(
    documents: Sequence[AnalysisDocument],
    *,
    feature_names: Sequence[str],
    count_matrix,
    config: HotspotConfig,
) -> TopicDiscoveryResult:
    if not documents:
        raise NoValidDocumentError("没有可用于热点主题发现的文章")
    if len(documents) <= 4:
        return _keyword_fallback(documents, config)
    if count_matrix is None or not feature_names:
        raise EmptyVocabularyError("热点主题发现词表为空")

    topic_counts = candidate_topic_counts(len(documents), config.max_topics)
    trained = []
    top_word_count = min(config.top_words, len(feature_names))
    for topic_count in topic_counts:
        model = LatentDirichletAllocation(
            n_components=topic_count,
            learning_method="batch",
            max_iter=config.lda_max_iter,
            random_state=config.random_state,
        )
        distribution = model.fit_transform(count_matrix)
        metrics = _topic_metrics(
            model, distribution, count_matrix, top_word_count, config
        )
        trained.append((model, distribution, metrics))

    (model, distribution, _metrics), warnings = _select_candidate(trained)
    if len(documents) < 10:
        warnings.append("SMALL_CORPUS")
    primary = np.asarray(distribution).argmax(axis=1)
    primary_counts = np.bincount(primary, minlength=model.n_components)
    probability_mass = np.asarray(distribution).sum(axis=0)
    topics = []
    for topic_index, component in enumerate(model.components_):
        indexes = component.argsort()[::-1][:top_word_count]
        total = float(component.sum()) or 1.0
        topics.append(
            DiscoveredTopic(
                topic_index=topic_index,
                keywords=[
                    {
                        "term": str(feature_names[index]),
                        "weight": round(float(component[index]) / total, 8),
                        "rank": rank,
                    }
                    for rank, index in enumerate(indexes, start=1)
                ],
                document_count=int(primary_counts[topic_index]),
                probability_mass=round(float(probability_mass[topic_index]), 8),
            )
        )
    assignments = []
    for document, row in zip(documents, np.asarray(distribution)):
        topic_index = int(row.argmax())
        probability = float(row[topic_index])
        assignment_warnings = []
        if probability < config.low_confidence_threshold:
            assignment_warnings.append("LOW_TOPIC_CONFIDENCE")
        assignments.append(
            ArticleTopicAssignment(
                article_id=document.article_id,
                topic_index=topic_index,
                probability=round(probability, 8),
                probabilities=[
                    {
                        "topic_index": int(index),
                        "probability": round(float(value), 8),
                    }
                    for index, value in enumerate(row)
                    if value >= 0.05 or index == topic_index
                ],
                warnings=assignment_warnings,
            )
        )
    return TopicDiscoveryResult(
        method="lda",
        selected_k=model.n_components,
        topics=topics,
        assignments=assignments,
        candidates=[item[2] for item in trained],
        warnings=list(dict.fromkeys(warnings)),
    )
