from __future__ import annotations

from typing import Sequence

from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer

from app.analysis.feature_config import FeatureConfig
from app.analysis.result import AnalysisDocument, FeatureMatrixResult, NoValidDocumentError


def _identity(tokens):
    return tokens


def build_feature_matrices(
    documents: Sequence[AnalysisDocument],
    config: FeatureConfig,
) -> FeatureMatrixResult:
    if not documents:
        raise NoValidDocumentError("没有可分析文章")

    document_ids = [document.article_id for document in documents]
    warnings: list[str] = []
    stats = {"document_count": len(documents)}
    if len(documents) == 1:
        warnings.append("SINGLE_DOCUMENT_FALLBACK")
        stats.update(vocabulary_size=0, effective_max_df=1.0, matrix_shape=None)
        return FeatureMatrixResult(
            document_ids=document_ids,
            feature_names=[],
            count_matrix=None,
            weighted_count_matrix=None,
            tfidf_matrix=None,
            warnings=warnings,
            stats=stats,
        )

    effective_max_df = (
        1.0 if len(documents) < config.minimum_normal_documents else config.max_df
    )
    if len(documents) < config.minimum_normal_documents:
        warnings.append("SMALL_CORPUS")

    combined_tokens = [document.title_tokens + document.body_tokens for document in documents]
    title_tokens = [document.title_tokens for document in documents]
    body_tokens = [document.body_tokens for document in documents]
    vectorizer = CountVectorizer(
        tokenizer=_identity,
        preprocessor=None,
        token_pattern=None,
        lowercase=False,
        max_features=config.max_features,
        ngram_range=config.ngram_range,
        min_df=config.min_df,
        max_df=effective_max_df,
        dtype="int64",
    )
    try:
        count_matrix = vectorizer.fit_transform(combined_tokens)
    except ValueError as exc:
        if "empty vocabulary" not in str(exc).lower() and "no terms remain" not in str(exc).lower():
            raise
        warnings.append("EMPTY_VOCABULARY")
        stats.update(vocabulary_size=0, effective_max_df=effective_max_df, matrix_shape=None)
        return FeatureMatrixResult(
            document_ids=document_ids,
            feature_names=[],
            count_matrix=None,
            weighted_count_matrix=None,
            tfidf_matrix=None,
            warnings=warnings,
            stats=stats,
        )

    title_matrix = vectorizer.transform(title_tokens).astype(float)
    body_matrix = vectorizer.transform(body_tokens).astype(float)
    weighted_count_matrix = (
        title_matrix.multiply(config.title_weight)
        + body_matrix.multiply(config.body_weight)
    ).tocsr()
    transformer = TfidfTransformer(
        norm="l2",
        use_idf=True,
        smooth_idf=config.smooth_idf,
        sublinear_tf=config.sublinear_tf,
    )
    tfidf_matrix = transformer.fit_transform(weighted_count_matrix).tocsr()
    feature_names = vectorizer.get_feature_names_out().tolist()
    stats.update(
        vocabulary_size=len(feature_names),
        effective_max_df=effective_max_df,
        matrix_shape=list(tfidf_matrix.shape),
    )
    return FeatureMatrixResult(
        document_ids=document_ids,
        feature_names=feature_names,
        count_matrix=count_matrix.tocsr(),
        weighted_count_matrix=weighted_count_matrix,
        tfidf_matrix=tfidf_matrix,
        warnings=warnings,
        stats=stats,
    )

