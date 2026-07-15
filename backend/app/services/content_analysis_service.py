from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Iterable

from flask import current_app

from app.analysis.embedding import BGEEncoder, normalize_vector
from app.analysis.feature_config import FeatureConfig
from app.analysis.feature_matrix import build_feature_matrices
from app.analysis.keyword_extractor import extract_article_keywords
from app.analysis.result import (
    AnalysisDocument,
    ContentAnalysisError,
    DatasetChangedError,
    EmbeddingUnavailableError,
    NoValidDocumentError,
)
from app.extensions import db
from app.models import (
    AnalysisRun,
    AnalysisRunArticle,
    Article,
    ArticleEmbedding,
    DocumentFeatures,
)
from app.preprocessing.segmenter import SEGMENT_VERSION, segment_document
from app.services.task_service import StaleTaskLeaseError, assert_task_lease


SEARCH_MATCH_VERSION = "search-keyword-v2"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sha256(value) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_keywords(items) -> list[dict]:
    output = []
    for item in items or []:
        if hasattr(item, "as_dict"):
            output.append(item.as_dict())
        elif isinstance(item, dict):
            output.append(dict(item))
        else:
            raise TypeError(
                f"unsupported keyword value: {type(item).__name__}"
            )
    return output


def _normalized_platforms(platforms: Iterable[str] | None) -> list[str]:
    return sorted(
        {
            item.strip().casefold()
            for item in (platforms or [])
            if isinstance(item, str) and item.strip()
        }
    )


def _config_from_app() -> FeatureConfig:
    return FeatureConfig(
        max_features=current_app.config.get("TFIDF_MAX_FEATURES", 5000),
        ngram_range=(1, current_app.config.get("TFIDF_NGRAM_MAX", 2)),
        min_df=current_app.config.get("TFIDF_MIN_DF", 1),
        max_df=current_app.config.get("TFIDF_MAX_DF", 0.90),
        sublinear_tf=current_app.config.get("TFIDF_SUBLINEAR_TF", True),
        smooth_idf=current_app.config.get("TFIDF_SMOOTH_IDF", True),
        title_weight=current_app.config.get("TFIDF_TITLE_WEIGHT", 1.0),
        body_weight=current_app.config.get("TFIDF_BODY_WEIGHT", 1.0),
        article_keyword_limit=current_app.config.get("ARTICLE_KEYWORD_LIMIT", 10),
        event_keyword_limit=current_app.config.get("EVENT_KEYWORD_LIMIT", 20),
        minimum_normal_documents=current_app.config.get(
            "CONTENT_ANALYSIS_MIN_NORMAL_DOCS", 5
        ),
    )


def _content_identity(article: Article) -> str:
    if article.latest_snapshot_id:
        return f"snapshot:{article.latest_snapshot_id}:v{article.content_version or 1}"
    return f"article:{article.id}:v{article.content_version or 1}"


def _feature_status(article: Article, features: DocumentFeatures | None) -> tuple[str, bool]:
    if article.clean_status != "success" or float(article.nlp_weight or 0) <= 0:
        return "skipped_invalid", False
    if article.duplicate_of_id is not None or bool(article.is_duplicate):
        return "skipped_duplicate", False
    if bool(article.is_advertisement):
        return "skipped_advertisement", False
    if features is None or not (features.tfidf_tokens or []):
        return "skipped_empty_tokens", False
    # 低质量内容过滤：内容过短无法提取有效语义
    content = (article.clean_content or article.raw_content or "").strip()
    title = (article.title or "").strip()
    # 社交平台放宽到 30 字（抖音/微博/小红书短内容常见）
    min_len = 30 if article.source_type == "social" else 50
    if len(content) < min_len:
        return "skipped_low_quality", False
    # 内容与标题几乎相同 → 无正文，纯转发/标题党（社交平台不检查）
    if article.source_type != "social" and len(content) < 120 and content[:40] == title[:40]:
        return "skipped_low_quality", False
    return "pending", True


def _query_fingerprint(mode, keyword, platforms) -> str:
    return _sha256(
        {
            "mode": (mode or "search").strip().casefold(),
            "keyword": " ".join((keyword or "").split()).casefold(),
            "platforms": _normalized_platforms(platforms),
            "search_match_version": SEARCH_MATCH_VERSION,
        }
    )


def query_fingerprint(mode, keyword, platforms) -> str:
    return _query_fingerprint(mode, keyword, platforms)


def _search_keyword_terms(keyword: str) -> list[str]:
    """提取用于标题匹配的关键词变体。

    返回两个列表：
    - full_terms: 完整关键词（英文边界匹配 or 去标点归一化匹配）
    - required_parts: 所有必须同时出现的字片段（中文≥2字关键词拆分后AND匹配）
    """
    aliases = {
        "人工智能": ["人工智能", "AI", "AIGC", "大模型"],
    }
    if keyword in aliases:
        return aliases[keyword]
    return [keyword]


def _jieba_segments(text: str) -> list[str]:
    """用 jieba 分词提取 ≥2 字的有意义片段。"""
    try:
        import jieba
        return [w for w in jieba.lcut(text) if len(w.strip()) >= 2]
    except Exception:
        # fallback: 每2字机械切分
        return [text[i:i+2] for i in range(0, len(text)-1, 2)]


def _title_matches_keyword(title: str, terms: list[str]) -> bool:
    """标题是否包含搜索关键词。

    策略：
    1. 完整归一化子串匹配（处理「台风巴威」vs 台风巴威）
    2. jieba 分词 + 松散匹配：≥60% 关键词单元命中
    """
    import re as _re
    folded = title.casefold()
    title_norm = _re.sub(r'[\s　「」【】《》""''、。，；：！？…—]+', '', folded)

    for term in terms:
        folded_term = term.casefold()
        # 英文：边界匹配
        if folded_term.isascii() and folded_term.isalnum():
            if _re.search(rf'(?<![a-z0-9]){_re.escape(folded_term)}(?![a-z0-9])', folded):
                return True
        # 完整中文子串 或 归一化后子串
        elif folded_term in folded:
            return True
        elif len(folded_term) >= 3:
            term_norm = _re.sub(r'[\s　「」【】《》""''、。，；：！？…—]+', '', folded_term)
            if term_norm and term_norm in title_norm:
                return True

    # jieba 分词松散匹配：≥60% 关键词单元在标题中出现即算命中
    kw_segments = _jieba_segments(terms[0]) if terms else []
    if len(kw_segments) >= 2:
        hits = sum(1 for s in kw_segments if s in folded)
        if hits / len(kw_segments) >= 0.6:
            return True

    return False


def create_analysis_run(
    article_ids: Iterable[int],
    *,
    user_id: int | None = None,
    mode: str = "search",
    keyword: str | None = None,
    platforms: Iterable[str] | None = None,
    source_task_id: int | None = None,
    config: FeatureConfig | None = None,
) -> tuple[AnalysisRun, bool]:
    config = config or _config_from_app()
    requested_ids = list(dict.fromkeys(int(article_id) for article_id in article_ids))
    if not requested_ids:
        raise NoValidDocumentError("没有指定可分析文章")
    normalized_platforms = _normalized_platforms(platforms)
    if mode == "search" and not normalized_platforms:
        raise ValueError("搜索分析必须选择至少一个平台")

    articles = Article.query.filter(Article.id.in_(requested_ids)).all()
    articles_by_id = {article.id: article for article in articles}
    missing = [article_id for article_id in requested_ids if article_id not in articles_by_id]
    if missing:
        raise KeyError(f"articles not found: {missing}")
    features_by_article = {
        row.article_id: row
        for row in DocumentFeatures.query.filter(
            DocumentFeatures.article_id.in_(requested_ids)
        ).all()
    }
    identities = [
        (article_id, _content_identity(articles_by_id[article_id]))
        for article_id in sorted(requested_ids)
    ]
    dataset_hash = _sha256(
        {
            "articles": identities,
            "segment_version": SEGMENT_VERSION,
            "config_hash": config.config_hash(),
            "search_match_version": SEARCH_MATCH_VERSION,
        }
    )
    fingerprint = _query_fingerprint(mode, keyword, normalized_platforms)
    reuse_query = AnalysisRun.query.filter(
        AnalysisRun.query_fingerprint == fingerprint,
        AnalysisRun.dataset_hash == dataset_hash,
        AnalysisRun.config_hash == config.config_hash(),
        AnalysisRun.status == "success",
    )
    if user_id is None:
        reuse_query = reuse_query.filter(AnalysisRun.user_id.is_(None))
    else:
        reuse_query = reuse_query.filter(AnalysisRun.user_id == user_id)
    existing = reuse_query.order_by(AnalysisRun.id.desc()).first()
    if existing is not None:
        return existing, True

    run = AnalysisRun(
        user_id=user_id,
        source_task_id=source_task_id,
        mode=mode,
        keyword=keyword,
        platforms=normalized_platforms,
        query_fingerprint=fingerprint,
        dataset_hash=dataset_hash,
        config_hash=config.config_hash(),
        article_count=len(requested_ids),
        representative_count=0,
        tfidf_config=config.as_dict(),
        versions={"algorithm": config.algorithm_version, "segment": SEGMENT_VERSION},
        statistics={},
        status="pending",
        warnings=[],
    )
    db.session.add(run)
    db.session.flush()

    # requested_ids 由当前采集/重试流程显式传入，是本次分析的数据边界。
    # 同一 URL 被再次抓取时会复用 Article 行，其 crawl_task_id 仍可能是首次任务；
    # 因此不能再按该单值字段过滤，否则强制刷新会把本轮文章全部排除。

    # 关键词相关性过滤：标题包含搜索关键词的才进入聚类（所有搜索模式都执行）
    if mode == "search" and keyword:
        kw = keyword.strip()
        kw_parts = _search_keyword_terms(kw)
        filtered_ids = []
        skipped = 0
        for article_id in requested_ids:
            article = articles_by_id.get(article_id)
            if article is None:
                continue
            title = (article.title or "")
            # 标题包含关键词或其任一部分即视为相关
            if _title_matches_keyword(title, kw_parts):
                filtered_ids.append(article_id)
            else:
                skipped += 1
        if skipped:
            run.warnings = (run.warnings or []) + [f"关键词「{kw}」过滤 {skipped} 篇标题不相关文章"]
        keyword_matched_ids = set(filtered_ids)
        requested_ids = [
            article_id
            for article_id in requested_ids
            if article_id in keyword_matched_ids
            or not _feature_status(
                articles_by_id[article_id], features_by_article.get(article_id)
            )[1]
        ]
    else:
        keyword_matched_ids = None

    representative_count = 0
    # 先查已有记录，避免重复插入
    existing_rows = {
        row.article_id: row
        for row in AnalysisRunArticle.query.filter_by(analysis_run_id=run.id).all()
    }
    for article_id in requested_ids:
        article = articles_by_id[article_id]
        status, representative = _feature_status(
            article, features_by_article.get(article_id)
        )
        representative_count += int(representative)
        if article_id in existing_rows:
            # 更新已有记录
            row = existing_rows[article_id]
            row.article_snapshot_id = article.latest_snapshot_id
            row.content_version = article.content_version or 1
            row.content_identity = _content_identity(article)
            row.is_representative = representative
            row.nlp_weight = float(article.nlp_weight or 0)
            row.feature_status = status
            continue
        db.session.add(
            AnalysisRunArticle(
                analysis_run_id=run.id,
                article_id=article.id,
                article_snapshot_id=article.latest_snapshot_id,
                content_version=article.content_version or 1,
                content_identity=_content_identity(article),
                is_representative=representative,
                nlp_weight=float(article.nlp_weight or 0),
                feature_status=status,
                keywords=[],
                warnings=[],
            )
        )
    run.representative_count = representative_count
    db.session.commit()
    if representative_count == 0:
        run.status = "failed"
        run.error_code = "NO_VALID_DOCUMENT"
        run.error_message = "没有符合内容分析条件的代表文章"
        run.completed_at = _utcnow()
        db.session.commit()
        raise NoValidDocumentError(run.error_message)
    return run, False


def _document_from_row(row: AnalysisRunArticle, article: Article, features: DocumentFeatures):
    title_result = segment_document(article.title or "")
    entities = {str(item): "entity" for item in (features.mentions or []) if str(item).strip()}
    return AnalysisDocument(
        article_id=article.id,
        snapshot_id=row.article_snapshot_id,
        content_version=row.content_version,
        title=article.title or "",
        title_tokens=title_result.data.get("tfidf_tokens") or [],
        body_tokens=features.tfidf_tokens or [],
        platform=article.platform,
        entities=entities,
        topics=features.topics or [],
        nlp_weight=float(row.nlp_weight or 0),
        warnings=list(title_result.warnings),
    )


def _verify_dataset(rows: list[AnalysisRunArticle], articles: dict[int, Article]) -> None:
    for row in rows:
        article = articles.get(row.article_id)
        if article is None or _content_identity(article) != row.content_identity:
            raise DatasetChangedError(f"文章 {row.article_id} 的内容版本已变化")


def _embedding_text(article: Article, maximum_length: int) -> str:
    text = f"{article.title or ''}\n{article.clean_content or ''}".strip()
    return text[: max(1, int(maximum_length))]


def _cache_embeddings(
    rows: list[AnalysisRunArticle],
    articles: dict[int, Article],
    encoder,
    maximum_length: int,
) -> None:
    missing_rows = []
    texts = []
    for row in rows:
        existing = ArticleEmbedding.query.filter_by(
            article_id=row.article_id,
            content_identity=row.content_identity,
            model_name=encoder.model_name,
            model_version=encoder.model_version,
            preprocess_version=encoder.preprocess_version,
        ).first()
        if existing is None:
            missing_rows.append(row)
            texts.append(_embedding_text(articles[row.article_id], maximum_length))
    if not missing_rows:
        return
    vectors = encoder.encode(texts)
    if len(vectors) != len(missing_rows):
        raise EmbeddingUnavailableError("嵌入返回数量与输入文章不一致")
    for row, vector in zip(missing_rows, vectors):
        normalized = normalize_vector(vector)
        db.session.add(
            ArticleEmbedding(
                article_id=row.article_id,
                article_snapshot_id=row.article_snapshot_id,
                content_version=row.content_version,
                content_identity=row.content_identity,
                model_name=encoder.model_name,
                model_version=encoder.model_version,
                preprocess_version=encoder.preprocess_version,
                dimension=len(normalized),
                vector=normalized,
            )
        )


def run_content_analysis(
    analysis_run_id: int,
    *,
    config: FeatureConfig | None = None,
    encoder=None,
    task_id: int | None = None,
) -> dict:
    assert_task_lease(task_id)
    run = db.session.get(AnalysisRun, analysis_run_id)
    if run is None:
        raise KeyError(f"analysis run not found: {analysis_run_id}")
    config = config or FeatureConfig(
        **{
            key: tuple(value) if key == "ngram_range" else value
            for key, value in (run.tfidf_config or {}).items()
        }
    )
    rows = AnalysisRunArticle.query.filter_by(analysis_run_id=run.id).order_by(
        AnalysisRunArticle.id
    ).all()
    representative_rows = [row for row in rows if row.is_representative]
    articles = {
        article.id: article
        for article in Article.query.filter(
            Article.id.in_([row.article_id for row in rows])
        ).all()
    }
    try:
        _verify_dataset(rows, articles)
        run.status = "running"
        run.started_at = run.started_at or _utcnow()
        run.error_code = None
        run.error_message = None
        db.session.commit()
        features_by_article = {
            item.article_id: item
            for item in DocumentFeatures.query.filter(
                DocumentFeatures.article_id.in_(
                    [row.article_id for row in representative_rows]
                )
            ).all()
        }
        documents = [
            _document_from_row(row, articles[row.article_id], features_by_article[row.article_id])
            for row in representative_rows
        ]
        matrix_result = build_feature_matrices(documents, config)
        keyword_map = extract_article_keywords(
            matrix_result,
            documents,
            config,
            query_terms=[run.keyword] if run.keyword else [],
        )
        # LLM 关键词提取（优先，TF-IDF 回退）
        try:
            from app.analysis.llm_keywords import extract_keywords_llm, _merge_llm_keywords
            llm_map = extract_keywords_llm(
                documents,
                batch_size=current_app.config.get("LLM_KEYWORD_BATCH_SIZE", 5),
            )
            if llm_map:
                keyword_map = _merge_llm_keywords(llm_map, keyword_map)
        except Exception:
            pass
        json_keyword_map = {
            article_id: _json_keywords(items)
            for article_id, items in keyword_map.items()
        }
        assert_task_lease(task_id)
        for row in representative_rows:
            row.keywords = json_keyword_map.get(row.article_id, [])
            row.feature_status = "success"
            row.warnings = list(
                dict.fromkeys((row.warnings or []) + documents[representative_rows.index(row)].warnings)
            )

        warnings = list(matrix_result.warnings)
        effective_encoder = encoder
        if effective_encoder is None and current_app.config.get("BGE_ENABLED", False):
            effective_encoder = BGEEncoder(
                current_app.config.get("BGE_MODEL", "BAAI/bge-small-zh-v1.5"),
                current_app.config.get("BGE_MODEL_VERSION", "default"),
                current_app.config.get("BGE_PREPROCESS_VERSION", "v1"),
            )
        if effective_encoder is not None:
            try:
                _cache_embeddings(
                    representative_rows,
                    articles,
                    effective_encoder,
                    current_app.config.get("BGE_MAX_TEXT_LENGTH", 2000),
                )
            except Exception:
                db.session.rollback()
                run = db.session.get(AnalysisRun, analysis_run_id)
                rows = AnalysisRunArticle.query.filter_by(analysis_run_id=run.id).order_by(
                    AnalysisRunArticle.id
                ).all()
                representative_rows = [row for row in rows if row.is_representative]
                for row in representative_rows:
                    row.keywords = json_keyword_map.get(row.article_id, [])
                    row.feature_status = "success"
                warnings.append("BGE_UNAVAILABLE")

        run.status = "success"
        run.warnings = list(dict.fromkeys(warnings))
        run.statistics = {
            **matrix_result.stats,
            "input_count": len(rows),
            "representative_count": len(representative_rows),
            "skipped_count": len(rows) - len(representative_rows),
        }
        run.completed_at = _utcnow()
        assert_task_lease(task_id)
        db.session.commit()
        return {
            "analysis_run_id": run.id,
            "status": run.status,
            "representative_count": len(representative_rows),
            "warnings": run.warnings or [],
            "statistics": run.statistics or {},
        }
    except StaleTaskLeaseError:
        db.session.rollback()
        raise
    except ContentAnalysisError as exc:
        db.session.rollback()
        run = db.session.get(AnalysisRun, analysis_run_id)
        run.status = "failed"
        run.error_code = exc.error_code
        run.error_message = str(exc)
        run.completed_at = _utcnow()
        db.session.commit()
        raise
    except Exception as exc:
        db.session.rollback()
        run = db.session.get(AnalysisRun, analysis_run_id)
        run.status = "failed"
        run.error_code = "CONTENT_ANALYSIS_ERROR"
        run.error_message = str(exc)
        run.completed_at = _utcnow()
        db.session.commit()
        raise


def _serialize_run(run: AnalysisRun, include_articles: bool = False) -> dict:
    data = {
        "id": run.id,
        "user_id": run.user_id,
        "mode": run.mode,
        "keyword": run.keyword,
        "platforms": run.platforms or [],
        "dataset_hash": run.dataset_hash,
        "config_hash": run.config_hash,
        "article_count": run.article_count,
        "representative_count": run.representative_count,
        "status": run.status,
        "warnings": run.warnings or [],
        "error_code": run.error_code,
        "error_message": run.error_message,
        "statistics": run.statistics or {},
        "created_at": run.created_at.isoformat(timespec="seconds") if run.created_at else None,
        "completed_at": run.completed_at.isoformat(timespec="seconds") if run.completed_at else None,
    }
    if include_articles:
        rows = AnalysisRunArticle.query.filter_by(analysis_run_id=run.id).order_by(
            AnalysisRunArticle.id
        ).all()
        data["articles"] = [
            {
                "article_id": row.article_id,
                "article_snapshot_id": row.article_snapshot_id,
                "content_version": row.content_version,
                "is_representative": row.is_representative,
                "feature_status": row.feature_status,
                "keywords": row.keywords or [],
                "warnings": row.warnings or [],
            }
            for row in rows
        ]
    return data


def get_analysis_run(
    analysis_run_id: int,
    *,
    user_id: int | None = None,
    admin: bool = False,
) -> dict | None:
    run = db.session.get(AnalysisRun, analysis_run_id)
    if run is None or (not admin and user_id is not None and run.user_id != user_id):
        return None
    return _serialize_run(run, include_articles=True)


def list_analysis_runs(
    *, user_id: int | None = None, admin: bool = False
) -> list[dict]:
    query = AnalysisRun.query
    if not admin and user_id is not None:
        query = query.filter(AnalysisRun.user_id == user_id)
    return [_serialize_run(run) for run in query.order_by(AnalysisRun.id.desc()).all()]
