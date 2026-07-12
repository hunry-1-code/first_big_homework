from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_PLATFORMS = (
    "weibo_hot",
    "weibo",
    "zhihu_hot",
    "zhihu",
    "bilibili",
    "xiaohongshu",
    "baidu_hot",
    "baidu",
)
HOT_PLATFORMS = {"weibo_hot", "zhihu_hot", "baidu_hot"}


def _redact(value: str, secrets: list[str] | None = None) -> str:
    text = str(value or "")
    for secret in secrets or []:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)bearer\s+[a-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    return text[:500]


def result_payload(
    platform: str,
    status: str,
    *,
    document_count: int = 0,
    preprocessing_status: str | None = None,
    message: str = "",
    contract_errors: list[str] | None = None,
    secrets: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "platform": platform,
        "status": status,
        "document_count": int(document_count),
        "preprocessing_status": preprocessing_status,
        "message": _redact(message, secrets),
        "contract_errors": list(contract_errors or []),
    }


def classify_error(error: Exception) -> str:
    code = str(getattr(error, "code", "")).upper()
    message = str(error).lower()
    combined = f"{code} {message}"
    if any(token in combined for token in ("401", "403", "AUTH", "UNAUTHORIZED", "INVALID KEY")):
        return "AUTH_ERROR"
    if any(token in combined for token in ("429", "QUOTA", "BALANCE", "RATE LIMIT", "LIMIT EXCEEDED")):
        return "QUOTA_ERROR"
    if any(token in combined for token in ("CAPTCHA", "LOGIN_REQUIRED", "BLOCKED", "SECURITY VERIFICATION")):
        return "PLATFORM_BLOCKED"
    if any(token in combined for token in ("TIMEOUT", "DNS", "SSL", "CONNECTION", "NETWORK")):
        return "NETWORK_ERROR"
    if any(token in combined for token in ("404", "NOT FOUND", "RESPONSE", "JSON", "SCHEMA")):
        return "REMOTE_CHANGED"
    return "CODE_ERROR"


def validate_document_contract(document) -> list[str]:
    errors = []
    for name in ("platform", "title", "source_type", "source_url"):
        value = getattr(document, name, None)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{name}_missing")
    raw_json = getattr(document, "raw_json", None)
    if not isinstance(raw_json, dict) or not raw_json:
        errors.append("raw_json_missing")
    return errors


def _secrets(config) -> list[str]:
    values = [
        getattr(config, "TIKHUB_API_KEY", ""),
        getattr(config, "ZHIHU_ACCESS_SECRET", ""),
        getattr(config, "QIANFAN_API_KEY", ""),
        getattr(config, "LLM_API_KEY", ""),
    ]
    values.extend(getattr(config, "TIKHUB_PLATFORM_API_KEYS", {}).values())
    return [value for value in values if value]


def validate_platform(registry, config, platform: str, keyword: str) -> dict[str, Any]:
    from app.crawler.base import CrawlRequest
    from app.preprocessing.pipeline import preprocess_document

    secrets = _secrets(config)
    if platform not in registry.platforms():
        return result_payload(
            platform,
            "CODE_ERROR",
            message="crawler not registered for current configuration",
            secrets=secrets,
        )
    request = CrawlRequest(
        platform=platform,
        keyword=None if platform in HOT_PLATFORMS else keyword,
        limit=1,
        mode="hot" if platform in HOT_PLATFORMS else "search",
    )
    try:
        documents = registry.get(platform).crawl(request)
        if not documents:
            return result_payload(platform, "EMPTY_SUCCESS", secrets=secrets)
        contract_errors = [
            error
            for document in documents
            for error in validate_document_contract(document)
        ]
        if contract_errors:
            return result_payload(
                platform,
                "CODE_ERROR",
                document_count=len(documents),
                message="adapter returned documents that violate RawDocument contract",
                contract_errors=sorted(set(contract_errors)),
                secrets=secrets,
            )
        output = preprocess_document(documents[0])
        status = "SUCCESS" if output.clean_status != "failed" else "CODE_ERROR"
        return result_payload(
            platform,
            status,
            document_count=len(documents),
            preprocessing_status=output.clean_status,
            message=output.clean_error or "",
            secrets=secrets,
        )
    except Exception as exc:
        return result_payload(
            platform,
            classify_error(exc),
            message=f"{type(exc).__name__}: {exc}",
            secrets=secrets,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Low-volume live crawler validator")
    parser.add_argument("--platform", action="append", choices=REQUIRED_PLATFORMS)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--keyword", default="人工智能")
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument("--output", default="crawl_live_validation_results.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from dotenv import load_dotenv

    env_path = Path(args.env_file).resolve()
    load_dotenv(env_path, override=True)
    from app.core.config import Config
    from app.crawler.factory import build_crawler_registry

    platforms = list(REQUIRED_PLATFORMS if args.all else (args.platform or []))
    if not platforms:
        raise SystemExit("specify --all or at least one --platform")
    registry = build_crawler_registry(Config)
    results = [validate_platform(registry, Config, platform, args.keyword) for platform in platforms]
    output_path = Path(args.output)
    output_path.write_text(
        json.dumps({"keyword": args.keyword, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if any(result["status"] == "CODE_ERROR" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
