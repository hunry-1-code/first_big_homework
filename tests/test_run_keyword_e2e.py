import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

from tools.run_keyword_e2e import (
    assess_frontend_data_quality,
    build_backend_environment,
    browser_artifact_names,
    browser_console_issues,
    build_search_payload,
    choose_relevant_cluster,
    safe_artifact,
    safe_slug,
    summarize_task,
)


class KeywordE2EDriverTest(unittest.TestCase):
    def test_cli_help_runs_from_repository_root(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "tools/run_keyword_e2e.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--keyword", result.stdout)

    def test_cluster_selection_prefers_relevant_movie_cluster(self):
        clusters = [
            {
                "id": 1,
                "title": "中国女足比赛",
                "member_count": 5,
                "keywords": ["女足", "比赛"],
            },
            {
                "id": 2,
                "title": "电影功夫女足定档",
                "member_count": 4,
                "keywords": ["功夫女足", "电影", "定档"],
            },
            {
                "id": 3,
                "title": "周星驰功夫足球回顾",
                "member_count": 8,
                "keywords": ["功夫足球", "旧片"],
            },
        ]

        selected = choose_relevant_cluster(clusters, "《功夫女足》电影")

        self.assertEqual(selected["id"], 2)
        self.assertGreaterEqual(selected["selection_score"], 6)

    def test_cluster_selection_rejects_unrelated_candidates(self):
        selected = choose_relevant_cluster(
            [
                {
                    "id": 1,
                    "title": "中国女足备战比赛",
                    "member_count": 2,
                    "keywords": ["女足", "比赛"],
                },
                {
                    "id": 2,
                    "title": "功夫足球经典片段",
                    "member_count": 3,
                    "keywords": ["功夫足球"],
                },
            ],
            "《功夫女足》电影",
        )

        self.assertIsNone(selected)

    def test_artifact_sanitizer_removes_credentials_and_tokens(self):
        value = {
            "token": "jwt-value",
            "password": "admin-secret",
            "safe": "Authorization: Bearer jwt-value",
            "nested": {"cookie": "session", "title": "功夫女足"},
        }

        sanitized = safe_artifact(
            value,
            ["jwt-value", "admin-secret", "session"],
        )
        serialized = json.dumps(sanitized, ensure_ascii=False)

        self.assertNotIn("jwt-value", serialized)
        self.assertNotIn("admin-secret", serialized)
        self.assertNotIn("Bearer", serialized)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("password", serialized.lower())
        self.assertNotIn("token", serialized.lower())
        self.assertNotIn("cookie", serialized.lower())
        self.assertEqual(sanitized["nested"]["title"], "功夫女足")

    def test_quality_gate_accepts_consistent_explainable_event(self):
        detail = {
            "title": "电影《功夫女足》定档",
            "summary": "影片发布定档信息并引发讨论。",
            "heat_index": 63.5,
            "lifecycle_stage": "成长期",
            "sentiment_positive": 0.4,
            "sentiment_negative": 0.2,
            "sentiment_neutral": 0.4,
            "trend": {"dates": ["07-12", "07-13"], "counts": [2, 3]},
            "platform": {
                "platforms": [
                    {"platform": "百度", "count": 3},
                    {"platform": "微博", "count": 2},
                ]
            },
            "keywords": {
                "keywords": [
                    {"word": "功夫女足", "source": "query"},
                    {"word": "电影定档", "source": "event"},
                    {"word": "主演阵容", "source": "event"},
                ]
            },
            "report": {
                "overview_text": "多平台报道聚焦影片定档和演员阵容。",
                "risk_data": {"score": 18, "level": "低风险"},
            },
            "articles": {
                "total": 5,
                "articles": [
                    {"title": "电影功夫女足定档", "clean_content": "电影正式定档"},
                    {"title": "功夫女足演员阵容", "clean_content": "影片主演公布"},
                    {"title": "功夫女足发布预告", "clean_content": "电影预告上线"},
                    {"title": "导演谈功夫女足", "clean_content": "影片创作"},
                    {"title": "中国女足比赛", "clean_content": "国家队备战"},
                ],
            },
        }
        propagation = {
            "coverage_status": "insufficient",
            "limitations": ["缺少平台原生转发链"],
            "graph": {"nodes": [{"id": 1}], "links": []},
        }
        dom = (
            "电影《功夫女足》定档 生命周期 成长期 多维舆情画像 "
            "可疑风险 低风险 传播证据不足 不代表已验证传播路径"
        )

        result = assess_frontend_data_quality(detail, propagation, dom)

        self.assertTrue(result["passed"])
        self.assertEqual(result["failed_rules"], [])
        self.assertGreaterEqual(result["metrics"]["article_relevance_ratio"], 0.7)

    def test_quality_gate_rejects_mock_and_invalid_frontend_values(self):
        detail = {
            "title": "功夫女足",
            "summary": "",
            "heat_index": math.nan,
            "lifecycle_stage": "",
            "sentiment_positive": 0.5,
            "sentiment_negative": 0.5,
            "sentiment_neutral": 0.5,
            "trend": {"dates": ["07-13"], "counts": []},
            "platform": {"platforms": [{"platform": "百度", "count": 3}]},
            "keywords": {
                "keywords": [{"word": "功夫女足", "source": "query"}]
            },
            "report": {"risk_data": {"score": 45, "level": "中风险"}},
            "articles": {"total": 3, "articles": []},
        }

        result = assess_frontend_data_quality(
            detail,
            propagation={"coverage_status": "insufficient", "limitations": []},
            dom_text="虚假风险 45 持续时间 45 undefined NaN",
        )

        self.assertFalse(result["passed"])
        expected = {
            "ARTICLE_RELEVANCE_LOW",
            "SINGLE_PLATFORM_WITHOUT_LIMITATION",
            "SENTIMENT_SUM_INVALID",
            "TREND_LENGTH_MISMATCH",
            "KEYWORD_DIVERSITY_LOW",
            "FIXED_RISK_PLACEHOLDER",
            "DOM_INVALID_VALUE",
        }
        self.assertTrue(expected.issubset(set(result["failed_rules"])))

    def test_quality_gate_requires_low_volume_lifecycle_disclosure(self):
        detail = {
            "title": "功夫女足上映",
            "summary": "影片上映引发讨论。",
            "heat_index": 20,
            "lifecycle_stage": "潜伏期",
            "lifecycle_confidence": 0.68,
            "lifecycle_evidence": {"low_volume": True},
            "sentiment_positive": 0.2,
            "sentiment_negative": 0.7,
            "sentiment_neutral": 0.1,
            "trend": {"dates": ["7/13"], "counts": [3]},
            "platform": {"platforms": [{"platform": "百度", "count": 3}]},
            "keywords": {
                "keywords": [
                    {"word": "功夫女足", "source": "event"},
                    {"word": "上映", "source": "event"},
                ]
            },
            "report": {"risk_data": {"score": 20, "level": "低风险"}},
            "articles": {
                "total": 3,
                "articles": [
                    {"title": "功夫女足电影上映", "clean_content": "影片上映"},
                    {"title": "功夫女足口碑", "clean_content": "电影讨论"},
                    {"title": "功夫女足票房", "clean_content": "影片票房"},
                ],
            },
        }
        result = assess_frontend_data_quality(
            detail,
            propagation={"coverage_status": "sufficient", "limitations": []},
            dom_text="功夫女足 潜伏期 风险评估",
        )

        self.assertIn("LIFECYCLE_LIMITATION_VISIBLE", result["failed_rules"])

    def test_safe_slug_handles_chinese_keyword_and_event_id(self):
        self.assertEqual(
            safe_slug("《功夫女足》电影", event_id=12),
            "功夫女足电影-event-12",
        )

    def test_browser_artifact_names_are_stable_and_filesystem_safe(self):
        names = browser_artifact_names("《功夫女足》电影", event_id=12)

        self.assertEqual(names["analysis"], "15_功夫女足电影-event-12_analysis.png")
        self.assertEqual(names["dashboard"], "15_功夫女足电影-event-12_dashboard.png")
        self.assertEqual(names["detail"], "15_功夫女足电影-event-12_detail.png")
        self.assertEqual(
            names["detail_middle"],
            "15_功夫女足电影-event-12_detail_middle.png",
        )
        self.assertEqual(
            names["detail_lower"],
            "15_功夫女足电影-event-12_detail_lower.png",
        )

    def test_browser_console_issues_keep_only_warnings_and_errors(self):
        issues = browser_console_issues(
            [
                {"level": "DEBUG", "message": "vite connected"},
                {
                    "level": "WARNING",
                    "message": "Extraneous non-props attributes (data-insp-path) were passed",
                },
                {"level": "WARNING", "message": "invalid prop"},
                {"level": "SEVERE", "message": "request failed"},
            ]
        )

        self.assertEqual([item["level"] for item in issues], ["WARNING", "SEVERE"])

    def test_backend_environment_is_isolated_and_asynchronous(self):
        env = build_backend_environment(
            {"PATH": "existing", "TASK_RECOVER_ON_STARTUP": "true"},
            "D:/runs/kungfu.db",
        )

        self.assertEqual(env["PATH"], "existing")
        self.assertEqual(env["DATABASE_URL"], "sqlite:///D:/runs/kungfu.db")
        self.assertEqual(env["TASK_RECOVER_ON_STARTUP"], "false")
        self.assertEqual(env["TASKS_RUN_SYNC"], "false")
        self.assertEqual(env["TASK_HEARTBEAT_ENABLED"], "false")
        self.assertEqual(env["AUTO_CREATE_DB"], "true")
        self.assertEqual(env["FLASK_DEBUG"], "0")

    def test_search_payload_matches_frontend_analysis_contract(self):
        payload = build_search_payload(
            "《功夫女足》电影",
            ["baidu", "weibo", "zhihu", "bilibili"],
            24,
        )

        self.assertEqual(
            payload,
            {
                "keyword": "《功夫女足》电影",
                "platforms": ["baidu", "weibo", "zhihu", "bilibili"],
                "target_count": 24,
            },
        )

    def test_task_summary_excludes_credentials_and_keeps_progress(self):
        task = {
            "id": 9,
            "status": "running",
            "progress": 68,
            "message": "正在处理",
            "payload": {"keyword": "《功夫女足》电影"},
            "lease_token": "private",
            "result": {"processed": 3},
        }

        summary = summarize_task(task)
        serialized = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["task_id"], 9)
        self.assertEqual(summary["progress"], 68)
        self.assertNotIn("private", serialized)
        self.assertNotIn("lease", serialized.lower())


if __name__ == "__main__":
    unittest.main()
