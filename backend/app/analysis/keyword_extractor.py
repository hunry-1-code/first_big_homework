from __future__ import annotations

import re
import unicodedata
import warnings
from collections import defaultdict
from typing import Callable, Iterable, Sequence

from app.analysis.feature_config import FeatureConfig
from app.analysis.result import (
    AnalysisDocument,
    ArticleKeyword,
    EventKeyword,
    FeatureMatrixResult,
)


_TEMPLATE_TERMS = {"点击", "查看", "责任编辑", "来源", "记者", "本文", "相关"}


def _normalize_term(term: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", term or "").casefold().split())


def _display_term(term: str) -> str:
    pieces = term.split()
    if len(pieces) > 1 and all(re.fullmatch(r"[\u4e00-\u9fff]+", item) for item in pieces):
        return "".join(pieces)
    return term


def _valid_term(term: str) -> bool:
    display = _display_term(term)
    if not display or display in _TEMPLATE_TERMS or re.fullmatch(r"\d+(?:\.\d+)?", display):
        return False
    if len(display) == 1 and re.fullmatch(r"[\u4e00-\u9fff]", display):
        return False
    return True


def _term_type(term: str, document: AnalysisDocument | None = None) -> str:
    display = _display_term(term)
    if document and display in document.entities:
        return document.entities[display]
    if display.startswith("#") and display.endswith("#"):
        return "hashtag"
    if " " in term:
        return "phrase"
    return "word"


def _default_textrank(text: str, limit: int) -> list[str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            warnings.simplefilter("ignore", ResourceWarning)
            import jieba.analyse

            return list(jieba.analyse.textrank(text, topK=limit, withWeight=False))
    except (ImportError, RuntimeError, ValueError):
        return []


def _normalize_scores(items: list[tuple[str, float, str, str]], limit: int) -> list[ArticleKeyword]:
    if not items:
        return []
    maximum = max(score for _, score, _, _ in items) or 1.0
    return [
        ArticleKeyword(
            term=_display_term(term),
            score=round(max(0.0, min(1.0, score / maximum)), 6),
            rank=index,
            source=source,
            type=term_type,
        )
        for index, (term, score, source, term_type) in enumerate(items[:limit], start=1)
    ]


def _suppress_contained_unigrams(items: list[tuple[str, float, str, str]]):
    phrases = [(term, score) for term, score, _, kind in items if kind == "phrase"]
    result = []
    for item in items:
        term, score, _, kind = item
        display = _display_term(term)
        if kind == "word" and any(display in _display_term(phrase) and phrase_score >= score for phrase, phrase_score in phrases):
            continue
        result.append(item)
    return result


def extract_article_keywords(
    matrix_result: FeatureMatrixResult,
    documents: Sequence[AnalysisDocument],
    config: FeatureConfig,
    query_terms: Iterable[str] = (),
    textrank_provider: Callable[[str, int], list[str]] | None = None,
) -> dict[int, list[ArticleKeyword]]:
    textrank_provider = textrank_provider or _default_textrank
    query_terms = [_normalize_term(term) for term in query_terms if _valid_term(_normalize_term(term))]
    query_display_terms = {_display_term(term) for term in query_terms}
    output: dict[int, list[ArticleKeyword]] = {}
    for row_index, document in enumerate(documents):
        candidates: dict[str, tuple[float, str, str]] = {}
        if matrix_result.tfidf_matrix is not None:
            row = matrix_result.tfidf_matrix.getrow(row_index)
            for index, score in zip(row.indices, row.data):
                term = _normalize_term(matrix_result.feature_names[index])
                if _valid_term(term):
                    candidates[term] = (float(score), "tfidf", _term_type(term, document))

        anchor_score = max((item[0] for item in candidates.values()), default=1.0)
        for term in query_terms:
            for existing in list(candidates):
                if _display_term(existing) == _display_term(term):
                    candidates.pop(existing)
            candidates[term] = (
                anchor_score * 0.6,
                "query",
                _term_type(term, document),
            )
        for term, entity_type in document.entities.items():
            normalized = _normalize_term(term)
            if _valid_term(normalized) and _display_term(normalized) not in query_display_terms:
                candidates[normalized] = (max(anchor_score * 0.95, candidates.get(normalized, (0.0, "", ""))[0]), "entity", entity_type)
        for term in document.topics:
            normalized = _normalize_term(term)
            if _valid_term(normalized) and _display_term(normalized) not in query_display_terms:
                candidates[normalized] = (max(anchor_score * 0.9, candidates.get(normalized, (0.0, "", ""))[0]), "topic", "hashtag")

        ranked = sorted(
            [(term, *details) for term, details in candidates.items()],
            key=lambda item: (-item[1], item[0]),
        )
        ranked = _suppress_contained_unigrams(ranked)
        seen = {_display_term(item[0]) for item in ranked}
        if len(ranked) < config.article_keyword_limit:
            for term in textrank_provider(document.analysis_text, config.article_keyword_limit * 2):
                normalized = _normalize_term(term)
                display = _display_term(normalized)
                if not _valid_term(normalized) or display in seen:
                    continue
                ranked.append((normalized, anchor_score * 0.5, "textrank", _term_type(normalized, document)))
                seen.add(display)
                if len(ranked) >= config.article_keyword_limit:
                    break
        output[document.article_id] = _normalize_scores(ranked, config.article_keyword_limit)
    return output


def aggregate_event_keywords(
    matrix_result: FeatureMatrixResult,
    event_mapping: dict[str, list[int]],
    documents: Sequence[AnalysisDocument],
    config: FeatureConfig,
) -> dict[str, list[EventKeyword]]:
    output: dict[str, list[EventKeyword]] = {}
    for event_id, indexes in event_mapping.items():
        if not indexes:
            output[event_id] = []
            continue
        scores = defaultdict(float)
        document_indexes = defaultdict(set)
        platform_indexes = defaultdict(set)
        types: dict[str, str] = {}
        sources: dict[str, str] = {}
        if matrix_result.tfidf_matrix is not None:
            for index in indexes:
                document = documents[index]
                row = matrix_result.tfidf_matrix.getrow(index)
                for term_index, value in zip(row.indices, row.data):
                    term = _normalize_term(matrix_result.feature_names[term_index])
                    if not _valid_term(term):
                        continue
                    display = _display_term(term)
                    scores[display] += float(value) * max(0.0, document.nlp_weight)
                    document_indexes[display].add(index)
                    platform_indexes[display].add(document.platform)
                    types[display] = _term_type(term, document)
                    sources[display] = "tfidf"
        for index in indexes:
            document = documents[index]
            for term, entity_type in document.entities.items():
                display = _display_term(_normalize_term(term))
                if _valid_term(display):
                    scores[display] += 0.25 * max(0.0, document.nlp_weight)
                    document_indexes[display].add(index)
                    platform_indexes[display].add(document.platform)
                    types[display] = entity_type
                    sources[display] = "entity"
            for term in document.topics:
                display = _display_term(_normalize_term(term))
                if _valid_term(display):
                    scores[display] += 0.2 * max(0.0, document.nlp_weight)
                    document_indexes[display].add(index)
                    platform_indexes[display].add(document.platform)
                    types[display] = "hashtag"
                    sources[display] = "topic"

        candidates = []
        for term, score in scores.items():
            count = len(document_indexes[term])
            kind = types.get(term, "word")
            if count < 2 and kind == "word":
                continue
            candidates.append((term, score, sources.get(term, "tfidf"), kind, count, len(platform_indexes[term])))
        candidates.sort(key=lambda item: (-item[1], -item[4], -item[5], item[0]))
        maximum = max((item[1] for item in candidates), default=1.0)
        output[event_id] = [
            EventKeyword(
                term=term,
                score=round(max(0.0, min(1.0, score / maximum)), 6),
                rank=rank,
                source=source,
                type=kind,
                document_count=count,
                document_ratio=round(count / len(indexes), 6),
                platform_count=platform_count,
            )
            for rank, (term, score, source, kind, count, platform_count) in enumerate(
                candidates[: config.event_keyword_limit], start=1
            )
        ]
    return output
