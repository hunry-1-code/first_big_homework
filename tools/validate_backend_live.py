from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVE_KEY = re.compile(
    r"authorization|api[-_]?key|access[-_]?token|secret|cookie",
    re.IGNORECASE,
)
SENSITIVE_TEXT = re.compile(
    r"authorization|bearer|cookie|api[-_]?key|access[-_]?token|secret",
    re.IGNORECASE,
)
BEARER_VALUE = re.compile(
    r"bearer\s+[a-z0-9._~+/=-]+",
    re.IGNORECASE,
)
HEADER_VALUE = re.compile(
    r"\b(?:authorization|cookie)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)


def make_isolated_config(base_config, database_uri: str):
    return type(
        "LiveValidationConfig",
        (base_config,),
        {
            "SQLALCHEMY_DATABASE_URI": str(database_uri),
            "AUTO_CREATE_DB": True,
            "TASK_RECOVER_ON_STARTUP": False,
            "TASKS_RUN_SYNC": True,
            "BGE_ENABLED": False,
        },
    )


def sanitize_result(value, secrets: list[str] | None = None):
    secrets = [str(secret) for secret in (secrets or []) if secret]
    if isinstance(value, dict):
        return {
            str(key): sanitize_result(item, secrets)
            for key, item in value.items()
            if not SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_result(item, secrets) for item in value]
    if isinstance(value, str):
        text = value
        for secret in secrets:
            text = text.replace(secret, "[REDACTED]")
        text = HEADER_VALUE.sub("[REDACTED]", text)
        text = BEARER_VALUE.sub("[REDACTED]", text)
        text = SENSITIVE_TEXT.sub("[REDACTED]", text)
        return text[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_result(str(value), secrets)


def contains_sensitive_text(text: str, secrets: list[str] | None = None) -> bool:
    value = str(text or "")
    if SENSITIVE_TEXT.search(value):
        return True
    return any(str(secret) in value for secret in (secrets or []) if secret)


def parse_llm_probe(content: str) -> bool:
    text = str(content or "").strip()
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text) == {"status": "ok"}
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def classify_external_error(error: Exception) -> str:
    combined = f"{getattr(error, 'code', '')} {error}".upper()
    if any(
        token in combined
        for token in ("401", "403", "AUTH", "UNAUTHORIZED", "INVALID KEY")
    ):
        return "AUTH_ERROR"
    if any(
        token in combined
        for token in ("429", "QUOTA", "RATE LIMIT", "LIMIT EXCEEDED", "BALANCE")
    ):
        return "QUOTA_ERROR"
    if any(
        token in combined
        for token in ("TIMEOUT", "CONNECTION", "DNS", "SSL", "NETWORK")
    ):
        return "NETWORK_ERROR"
    if any(
        token in combined
        for token in (
            "JSON",
            "STRUCTURE",
            "FORMAT",
            "CONTENT IS EMPTY",
            "内容为空",
            "结构不合法",
        )
    ):
        return "FORMAT_ERROR"
    return "INTERNAL_ERROR"


def configured_secrets(config) -> list[str]:
    values = [
        getattr(config, "TIKHUB_API_KEY", ""),
        getattr(config, "ZHIHU_ACCESS_SECRET", ""),
        getattr(config, "QIANFAN_API_KEY", ""),
        getattr(config, "LLM_API_KEY", ""),
    ]
    values.extend(
        getattr(config, "TIKHUB_PLATFORM_API_KEYS", {}).values()
    )
    return sorted({str(value) for value in values if value})


def run_daily_hot_probe(config_class) -> dict[str, Any]:
    from app import create_app
    from app.extensions import db
    from app.services.daily_hot_service import (
        collect_daily_hot,
        serialize_daily_hot_run,
    )

    app = create_app(config_class)
    try:
        database_uri = str(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
        scheduler_started = "task_recovery_scheduler" in app.extensions
        if (
            app.config.get("TASK_RECOVER_ON_STARTUP")
            or not app.config.get("TASKS_RUN_SYNC")
            or app.config.get("BGE_ENABLED")
            or not database_uri.startswith("sqlite:")
            or scheduler_started
        ):
            raise RuntimeError("isolated validation runtime is invalid")

        with app.app_context():
            run = collect_daily_hot(
                sources=["weibo_hot", "baidu_hot", "zhihu_hot"],
                source_limit=1,
                result_limit=1,
                rrf_k=60,
                ttl_seconds=0,
                force=True,
            )
            payload = serialize_daily_hot_run(
                run,
                limit=1,
                ttl_seconds=900,
            )
            return {
                "status": run.status,
                "available_sources": run.available_sources or [],
                "failed_sources": run.failed_sources or [],
                "item_count": int(run.item_count or 0),
                "returned_items": len(payload["items"]),
                "has_event_id_field": bool(payload["items"])
                and "event_id" in payload["items"][0],
                "scheduler_started": scheduler_started,
            }
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def run_llm_probe(config_class, *, client_factory=None) -> dict[str, Any]:
    if client_factory is None:
        from app.llm.client import LLMClient

        client_factory = LLMClient
    try:
        client = client_factory(
            api_key=getattr(config_class, "LLM_API_KEY", ""),
            base_url=getattr(config_class, "LLM_BASE_URL", ""),
            model_name=getattr(config_class, "LLM_MODEL_NAME", ""),
            timeout=getattr(config_class, "LLM_REQUEST_TIMEOUT", 30),
        )
        response = client.chat(
            [
                {
                    "role": "system",
                    "content": "Return only compact JSON. Do not add Markdown.",
                },
                {
                    "role": "user",
                    "content": 'Return exactly {"status":"ok"}.',
                },
            ],
            temperature=0,
            max_tokens=30,
        )
        valid = parse_llm_probe(response.get("content", ""))
        return {
            "status": "SUCCESS" if valid else "FORMAT_ERROR",
            "model": str(
                response.get("model")
                or getattr(config_class, "LLM_MODEL_NAME", "")
            )[:100],
            "content_valid": valid,
        }
    except Exception as exc:
        return {
            "status": classify_external_error(exc),
            "model": str(getattr(config_class, "LLM_MODEL_NAME", ""))[:100],
            "content_valid": False,
            "message": f"{type(exc).__name__}: {exc}"[:500],
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Secret-safe isolated backend live validator"
    )
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument(
        "--output",
        default="tests/final_backend_live_validation_results.json",
    )
    parser.add_argument("--skip-top10", action="store_true")
    parser.add_argument("--skip-llm", action="store_true")
    return parser.parse_args()


def _outcome_is_internal_failure(result: dict[str, Any]) -> bool:
    failing = {"INTERNAL_ERROR", "FORMAT_ERROR"}
    return any(
        isinstance(value, dict) and value.get("status") in failing
        for value in result.values()
    )


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from dotenv import load_dotenv

    load_dotenv(Path(args.env_file).resolve(), override=True)
    from app.core.config import Config

    secrets = configured_secrets(Config)
    result: dict[str, Any] = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    with tempfile.TemporaryDirectory(prefix="opinion-live-validation-") as directory:
        database_path = Path(directory) / "validation.db"
        isolated_config = make_isolated_config(
            Config,
            f"sqlite:///{database_path.as_posix()}",
        )
        if args.skip_top10:
            result["daily_hot"] = {"status": "SKIPPED"}
        else:
            try:
                result["daily_hot"] = run_daily_hot_probe(isolated_config)
            except Exception as exc:
                result["daily_hot"] = {
                    "status": classify_external_error(exc),
                    "message": f"{type(exc).__name__}: {exc}"[:500],
                }
        if args.skip_llm:
            result["llm"] = {"status": "SKIPPED"}
        else:
            result["llm"] = run_llm_probe(isolated_config)

    sanitized = sanitize_result(result, secrets)
    serialized = json.dumps(sanitized, ensure_ascii=False, indent=2)
    if contains_sensitive_text(serialized, secrets):
        print('{"status":"SAFETY_SCAN_FAILED"}')
        return 1

    sanitized["safety_scan_passed"] = True
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(sanitized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(sanitized, ensure_ascii=False, indent=2))
    return 1 if _outcome_is_internal_failure(sanitized) else 0


if __name__ == "__main__":
    raise SystemExit(main())
