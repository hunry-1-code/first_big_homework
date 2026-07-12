from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ContentAnalysisError(RuntimeError):
    error_code = "CONTENT_ANALYSIS_ERROR"


class NoValidDocumentError(ContentAnalysisError):
    error_code = "NO_VALID_DOCUMENT"


class EmptyVocabularyError(ContentAnalysisError):
    error_code = "EMPTY_VOCABULARY"


class DatasetChangedError(ContentAnalysisError):
    error_code = "DATASET_CHANGED"


class EmbeddingUnavailableError(ContentAnalysisError):
    error_code = "BGE_UNAVAILABLE"


@dataclass(slots=True)
class AnalysisDocument:
    article_id: int
    snapshot_id: int | None
    content_version: int
    title: str
    title_tokens: list[str]
    body_tokens: list[str]
    platform: str
    entities: dict[str, str] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    nlp_weight: float = 1.0
    warnings: list[str] = field(default_factory=list)

    @property
    def analysis_text(self) -> str:
        return " ".join([self.title, *self.body_tokens]).strip()


@dataclass(slots=True)
class FeatureMatrixResult:
    document_ids: list[int]
    feature_names: list[str]
    count_matrix: Any | None
    weighted_count_matrix: Any | None
    tfidf_matrix: Any | None
    warnings: list[str]
    stats: dict[str, Any]


@dataclass(slots=True)
class ArticleKeyword:
    term: str
    score: float
    rank: int
    source: str
    type: str

    def as_dict(self) -> dict:
        return {
            "term": self.term,
            "score": self.score,
            "rank": self.rank,
            "source": self.source,
            "type": self.type,
        }


@dataclass(slots=True)
class EventKeyword(ArticleKeyword):
    document_count: int = 0
    document_ratio: float = 0.0
    platform_count: int = 0

    def as_dict(self) -> dict:
        data = super().as_dict()
        data.update(
            document_count=self.document_count,
            document_ratio=self.document_ratio,
            platform_count=self.platform_count,
        )
        return data

