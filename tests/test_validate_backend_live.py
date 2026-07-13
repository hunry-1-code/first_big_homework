import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tools.validate_backend_live import (
    _outcome_is_internal_failure,
    classify_external_error,
    configured_secrets,
    contains_sensitive_text,
    make_isolated_config,
    parse_llm_probe,
    run_daily_hot_probe,
    run_llm_probe,
    sanitize_result,
)


class FakeError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class BackendLiveValidatorTest(unittest.TestCase):
    def test_isolated_config_disables_long_running_services(self):
        class Base:
            TASK_RECOVER_ON_STARTUP = True
            TASKS_RUN_SYNC = False
            BGE_ENABLED = True
            AUTO_CREATE_DB = False
            SQLALCHEMY_DATABASE_URI = "sqlite:///development.db"

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "validation.db"
            config = make_isolated_config(
                Base,
                f"sqlite:///{database.as_posix()}",
            )

        self.assertFalse(config.TASK_RECOVER_ON_STARTUP)
        self.assertTrue(config.TASKS_RUN_SYNC)
        self.assertFalse(config.BGE_ENABLED)
        self.assertTrue(config.AUTO_CREATE_DB)
        self.assertIn("validation.db", config.SQLALCHEMY_DATABASE_URI)

    def test_result_sanitization_removes_sensitive_keys_and_values(self):
        value = {
            "message": "Authorization: Bearer real-secret",
            "nested": {
                "api_key": "real-secret",
                "safe": "cookie=session-value",
            },
        }

        sanitized = sanitize_result(value, ["real-secret", "session-value"])
        serialized = json.dumps(sanitized, ensure_ascii=False)

        self.assertNotIn("real-secret", serialized)
        self.assertNotIn("session-value", serialized)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("Bearer", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("cookie", serialized.lower())
        self.assertEqual(sanitized["nested"]["safe"], "[REDACTED]")

    def test_sensitive_scan_detects_markers_and_known_values(self):
        self.assertTrue(
            contains_sensitive_text(
                '{"message":"Bearer hidden"}',
                ["another-secret"],
            )
        )
        self.assertTrue(
            contains_sensitive_text(
                '{"message":"another-secret"}',
                ["another-secret"],
            )
        )
        self.assertFalse(
            contains_sensitive_text(
                '{"status":"success","model":"configured"}',
                ["another-secret"],
            )
        )

    def test_llm_probe_accepts_only_exact_minimal_json(self):
        self.assertTrue(parse_llm_probe('{"status":"ok"}'))
        self.assertTrue(parse_llm_probe('```json\n{"status":"ok"}\n```'))
        self.assertFalse(parse_llm_probe('{"status":"maybe"}'))
        self.assertFalse(parse_llm_probe('{"status":"ok","extra":true}'))
        self.assertFalse(parse_llm_probe("not-json"))

    def test_external_error_classification_is_stable(self):
        cases = [
            (FakeError("HTTP_401", "unauthorized"), "AUTH_ERROR"),
            (FakeError("HTTP_429", "quota exceeded"), "QUOTA_ERROR"),
            (FakeError("REQUEST_TIMEOUT", "network timeout"), "NETWORK_ERROR"),
            (FakeError("INVALID_JSON", "response format"), "FORMAT_ERROR"),
            (FakeError("UNKNOWN", "unexpected state"), "INTERNAL_ERROR"),
        ]

        for error, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_external_error(error), expected)

    def test_configured_secrets_are_unique_and_ignore_empty_values(self):
        config = SimpleNamespace(
            TIKHUB_API_KEY="shared",
            ZHIHU_ACCESS_SECRET="",
            QIANFAN_API_KEY="qianfan",
            LLM_API_KEY="shared",
            TIKHUB_PLATFORM_API_KEYS={
                "weibo": "platform",
                "douyin": "",
            },
        )

        self.assertEqual(
            configured_secrets(config),
            ["platform", "qianfan", "shared"],
        )

    def test_daily_hot_probe_uses_minimum_limits_without_scheduler(self):
        class Config:
            TESTING = True
            SECRET_KEY = "test"
            JWT_SECRET_KEY = "test"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            AUTO_CREATE_DB = True
            FRONTEND_ORIGINS = ["http://localhost"]
            TASK_RECOVER_ON_STARTUP = False
            TASKS_RUN_SYNC = True
            BGE_ENABLED = False

        run = SimpleNamespace(
            status="success",
            available_sources=["baidu_hot", "weibo_hot", "zhihu_hot"],
            failed_sources=[],
            item_count=1,
        )
        payload = {"items": [{"event_id": None}]}
        with patch(
            "app.services.daily_hot_service.collect_daily_hot",
            return_value=run,
        ) as collect, patch(
            "app.services.daily_hot_service.serialize_daily_hot_run",
            return_value=payload,
        ) as serialize:
            result = run_daily_hot_probe(Config)

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["scheduler_started"])
        self.assertTrue(result["has_event_id_field"])
        self.assertEqual(
            collect.call_args.kwargs,
            {
                "sources": ["weibo_hot", "baidu_hot", "zhihu_hot"],
                "source_limit": 1,
                "result_limit": 1,
                "rrf_k": 60,
                "ttl_seconds": 0,
                "force": True,
            },
        )
        serialize.assert_called_once_with(run, limit=1, ttl_seconds=900)

    def test_daily_hot_probe_releases_temporary_sqlite_file(self):
        directory = Path(tempfile.mkdtemp(prefix="live-validator-test-"))
        database = directory / "validation.db"

        class BaseConfig:
            TESTING = True
            SECRET_KEY = "test"
            JWT_SECRET_KEY = "test"
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            FRONTEND_ORIGINS = ["http://localhost"]

        config = make_isolated_config(
            BaseConfig,
            f"sqlite:///{database.as_posix()}",
        )
        run = SimpleNamespace(
            status="success",
            available_sources=["weibo_hot"],
            failed_sources=[],
            item_count=1,
        )
        try:
            with patch(
                "app.services.daily_hot_service.collect_daily_hot",
                return_value=run,
            ), patch(
                "app.services.daily_hot_service.serialize_daily_hot_run",
                return_value={"items": [{"event_id": None}]},
            ):
                run_daily_hot_probe(config)

            database.unlink()
            self.assertFalse(database.exists())
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_llm_probe_makes_one_minimal_structured_call(self):
        class Config:
            LLM_API_KEY = "configured"
            LLM_BASE_URL = "https://example.com"
            LLM_MODEL_NAME = "test-model"
            LLM_REQUEST_TIMEOUT = 7

        class FakeClient:
            instances = []

            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.calls = []
                self.__class__.instances.append(self)

            def chat(self, messages, **kwargs):
                self.calls.append((messages, kwargs))
                return {"content": '{"status":"ok"}', "model": "live-model"}

        result = run_llm_probe(Config, client_factory=FakeClient)

        client = FakeClient.instances[0]
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["model"], "live-model")
        self.assertTrue(result["content_valid"])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.kwargs["timeout"], 7)
        self.assertEqual(client.calls[0][1], {"temperature": 0, "max_tokens": 30})

    def test_llm_probe_reports_format_error_without_returning_content(self):
        class Config:
            LLM_API_KEY = "configured"
            LLM_BASE_URL = "https://example.com"
            LLM_MODEL_NAME = "test-model"
            LLM_REQUEST_TIMEOUT = 7

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def chat(self, messages, **kwargs):
                return {"content": "not-json", "model": "live-model"}

        result = run_llm_probe(Config, client_factory=FakeClient)

        self.assertEqual(result["status"], "FORMAT_ERROR")
        self.assertFalse(result["content_valid"])
        self.assertNotIn("content", result)

    def test_only_internal_and_format_outcomes_fail_the_validator(self):
        self.assertFalse(
            _outcome_is_internal_failure(
                {"daily_hot": {"status": "failed"}, "llm": {"status": "AUTH_ERROR"}}
            )
        )
        self.assertTrue(
            _outcome_is_internal_failure(
                {"daily_hot": {"status": "success"}, "llm": {"status": "FORMAT_ERROR"}}
            )
        )


if __name__ == "__main__":
    unittest.main()
