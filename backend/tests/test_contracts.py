import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.import_service import validate_json_documents
from app.services.task_service import (
    create_task,
    get_task,
    list_tasks,
    reset_task_store,
    update_task,
)


class ImportServiceContractTest(unittest.TestCase):
    def test_valid_sample_json_is_normalized_for_article_pipeline(self):
        documents = [
            {
                "platform": "news",
                "url": "https://example.com/news/1",
                "title": "某地公共事件引发关注",
                "raw_content": "<p>现场处置正在推进。</p>",
                "publish_time": "2026-07-10T08:00:00+08:00",
                "author": "示例媒体",
            }
        ]

        normalized, errors = validate_json_documents(documents)

        self.assertEqual(errors, [])
        self.assertEqual(normalized[0]["clean_status"], "pending")
        self.assertEqual(normalized[0]["clean_content"], "")
        self.assertEqual(normalized[0]["raw_json"]["author"], "示例媒体")

    def test_invalid_sample_json_reports_missing_required_fields(self):
        normalized, errors = validate_json_documents(
            [
                {
                    "platform": "news",
                    "title": "缺少 URL 和发布时间",
                    "raw_content": "正文",
                }
            ]
        )

        self.assertEqual(normalized, [])
        self.assertEqual(errors[0]["index"], 0)
        self.assertEqual(errors[0]["missing"], ["url", "publish_time"])


class TaskServiceContractTest(unittest.TestCase):
    def setUp(self):
        reset_task_store()

    def test_create_and_update_task_keeps_queryable_status(self):
        task = create_task(
            task_type="sample_import",
            created_by=3,
            payload={"filename": "opinion_events.sample.json"},
        )

        self.assertEqual(task["id"], 1)
        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["progress"], 0)

        updated = update_task(
            task["id"],
            status="running",
            progress=40,
            message="正在清洗样例数据",
        )

        self.assertEqual(updated["status"], "running")
        self.assertEqual(get_task(task["id"])["message"], "正在清洗样例数据")

    def test_list_tasks_can_filter_current_user_tasks(self):
        create_task("keyword_crawl", created_by=1, payload={"keyword": "AI"})
        create_task("sample_import", created_by=2, payload={"filename": "demo.json"})

        tasks = list_tasks(created_by=1)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["type"], "keyword_crawl")


if __name__ == "__main__":
    unittest.main()
