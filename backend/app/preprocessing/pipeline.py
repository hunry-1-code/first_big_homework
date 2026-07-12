from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.crawler.base import RawDocument
from app.crawler.errors import detect_blocked_content
from app.preprocessing.cleaner import clean_document
from app.preprocessing.deduplicator import compare_documents, compute_content_hash, simhash_text
from app.preprocessing.extractor import extract_content
from app.preprocessing.normalizer import normalize_document
from app.preprocessing.quality import evaluate_quality
from app.preprocessing.result import StageResult
from app.preprocessing.segmenter import segment_document


PREPROCESS_VERSION = "v1"


@dataclass(slots=True)
class ProcessingStageLog:
    stage: str
    status: str
    error_code: str | None = None
    message: str | None = None
    retryable: bool = False
    duration_ms: int = 0


@dataclass(slots=True)
class PipelineOutput:
    raw_content: str
    normalized_data: dict[str, Any] = field(default_factory=dict)
    clean_content: str = ""
    clean_status: str = "pending"
    clean_error: str | None = None
    extraction_method: str | None = None
    extraction_degraded: bool = False
    processing_warnings: list[str] = field(default_factory=list)
    normalize_version: str = "v1"
    preprocess_version: str = PREPROCESS_VERSION
    quality: dict[str, Any] = field(default_factory=dict)
    duplicate: dict[str, Any] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    logs: list[ProcessingStageLog] = field(default_factory=list)


def _run_stage(
    stage: str,
    function: Callable[[], StageResult],
    logs: list[ProcessingStageLog],
) -> StageResult:
    started = time.perf_counter()
    try:
        result = function()
    except Exception as exc:
        result = StageResult.failed([f"{stage.upper()}_UNEXPECTED_ERROR"])
        result.warnings.append(str(exc))
    duration_ms = int((time.perf_counter() - started) * 1000)
    logs.append(
        ProcessingStageLog(
            stage=stage,
            status=result.status,
            error_code=result.errors[0] if result.errors else None,
            message="; ".join([*result.errors, *result.warnings]) or None,
            retryable=False,
            duration_ms=duration_ms,
        )
    )
    return result


def _failed_output(
    raw_content: str,
    normalized_data: dict[str, Any],
    result: StageResult,
    logs: list[ProcessingStageLog],
) -> PipelineOutput:
    return PipelineOutput(
        raw_content=raw_content,
        normalized_data=normalized_data,
        clean_status="failed",
        clean_error=result.errors[0] if result.errors else "PREPROCESS_FAILED",
        processing_warnings=list(dict.fromkeys(result.warnings)),
        logs=logs,
    )


def preprocess_document(
    document: RawDocument | dict[str, Any],
    duplicate_candidates: list[dict[str, Any]] | None = None,
) -> PipelineOutput:
    raw_content = (
        document.raw_content if isinstance(document, RawDocument) else str(document.get("raw_content") or "")
    )
    logs: list[ProcessingStageLog] = []
    warnings: list[str] = []

    fetch_status = document.fetch_status if isinstance(document, RawDocument) else document.get("fetch_status", "success")
    fetch_error = document.fetch_error if isinstance(document, RawDocument) else document.get("fetch_error")
    crawl_error = fetch_error if fetch_status == "failed" else detect_blocked_content(raw_content)
    if crawl_error:
        logs.append(
            ProcessingStageLog(
                stage="crawl",
                status="failed",
                error_code=crawl_error,
                message="acquisition returned a blocked or failed page",
            )
        )
        return PipelineOutput(
            raw_content=raw_content,
            clean_status="failed",
            clean_error=crawl_error,
            logs=logs,
        )
    logs.append(ProcessingStageLog(stage="crawl", status="success"))

    normalized = _run_stage("normalize", lambda: normalize_document(document), logs)
    warnings.extend(normalized.warnings)
    if normalized.status == "failed":
        return _failed_output(raw_content, normalized.data, normalized, logs)
    data = normalized.data

    extracted = _run_stage(
        "extract",
        lambda: extract_content(
            data.get("raw_content", ""),
            data.get("content_type", "html"),
            data.get("source_type", "news"),
            data.get("platform"),
        ),
        logs,
    )
    warnings.extend(extracted.warnings)
    if extracted.status == "failed":
        output = _failed_output(raw_content, data, extracted, logs)
        output.processing_warnings = list(dict.fromkeys(warnings))
        return output

    cleaned = _run_stage(
        "clean",
        lambda: clean_document(extracted.data["text"], data.get("platform")),
        logs,
    )
    warnings.extend(cleaned.warnings)
    if cleaned.status == "failed":
        output = _failed_output(raw_content, data, cleaned, logs)
        output.extraction_method = extracted.data.get("extraction_method")
        output.extraction_degraded = extracted.data.get("extraction_degraded", False)
        output.processing_warnings = list(dict.fromkeys(warnings))
        return output

    clean_content = cleaned.data["clean_content"]
    quality = _run_stage(
        "quality",
        lambda: evaluate_quality(
            clean_content,
            data.get("source_type", "news"),
            data,
            extracted.data.get("extraction_method", "fallback"),
            extracted.data.get("extraction_degraded", False),
            cleaned.data.get("statistics"),
        ),
        logs,
    )
    warnings.extend(quality.warnings)

    content_hash = compute_content_hash(clean_content)
    simhash_value = f"{simhash_text(clean_content):016x}"
    duplicate = {
        "is_duplicate": False,
        "duplicate_of_id": None,
        "duplicate_group_id": None,
        "duplicate_method": None,
        "duplicate_score": 0.0,
        "content_hash": content_hash,
        "simhash": simhash_value,
        "dedup_version": "v1",
        "dedup_pending": False,
    }
    dedup_started = time.perf_counter()
    for candidate in duplicate_candidates or []:
        comparison = compare_documents(
            data.get("title", ""),
            clean_content,
            candidate.get("title", ""),
            candidate.get("clean_content", ""),
        )
        if comparison.is_duplicate:
            representative_id = candidate.get("id")
            duplicate.update(
                {
                    "is_duplicate": True,
                    "duplicate_of_id": representative_id,
                    "duplicate_group_id": candidate.get("duplicate_group_id")
                    or (f"group-{representative_id}" if representative_id is not None else str(uuid.uuid4())),
                    "duplicate_method": comparison.method,
                    "duplicate_score": comparison.score,
                }
            )
            break
        if comparison.dedup_pending:
            duplicate["dedup_pending"] = True
    logs.append(
        ProcessingStageLog(
            stage="deduplicate",
            status="degraded" if duplicate["dedup_pending"] else "success",
            error_code="DEDUP_BGE_UNAVAILABLE" if duplicate["dedup_pending"] else None,
            message="BGE boundary review pending" if duplicate["dedup_pending"] else None,
            duration_ms=int((time.perf_counter() - dedup_started) * 1000),
        )
    )
    if duplicate["dedup_pending"]:
        warnings.append("DEDUP_BGE_UNAVAILABLE")

    segmented = _run_stage(
        "segment",
        lambda: segment_document(
            clean_content,
            topics=cleaned.data.get("topics"),
            mentions=cleaned.data.get("mentions"),
        ),
        logs,
    )
    warnings.extend(segmented.warnings)
    if segmented.status == "failed":
        output = _failed_output(raw_content, data, segmented, logs)
        output.clean_content = clean_content
        output.quality = quality.data
        output.duplicate = duplicate
        return output

    return PipelineOutput(
        raw_content=raw_content,
        normalized_data=data,
        clean_content=clean_content,
        clean_status="success",
        clean_error=None,
        extraction_method=extracted.data.get("extraction_method"),
        extraction_degraded=extracted.data.get("extraction_degraded", False),
        processing_warnings=list(dict.fromkeys(warnings)),
        normalize_version=normalized.version,
        preprocess_version=PREPROCESS_VERSION,
        quality=quality.data,
        duplicate=duplicate,
        features=segmented.data,
        logs=logs,
    )
