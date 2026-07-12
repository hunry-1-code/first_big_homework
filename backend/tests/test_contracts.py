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
from app.core.config import Config
from app.services.api_contract_service import api_platform_name, api_lifecycle_stage, normalized_sentiment, api_sentiment_label, clamp_heat, trend_key_points

class ApiOutputContractTest(unittest.TestCase):
    def test_maps_contract_enums_and_values(self):
        self.assertEqual(api_platform_name('weibo_hot'),'微博热搜')
        self.assertEqual(api_lifecycle_stage('高潮期'),'爆发期')
        self.assertEqual(api_sentiment_label('中立'),'中性')
        self.assertEqual(clamp_heat(120),100.0)
        self.assertEqual(sum(normalized_sentiment(2,1,1)),1.0)
    def test_builds_trend_key_points(self):
        self.assertEqual(len(trend_key_points(['7/1','7/2','7/3'],[1,5,2])),3)


class QianfanConfigContractTest(unittest.TestCase):
    def test_qianfan_api_configuration_is_available(self):
        self.assertTrue(hasattr(Config, "QIANFAN_API_KEY"))
        self.assertEqual(
            Config.QIANFAN_API_BASE_URL, "https://qianfan.baidubce.com"
        )
        self.assertEqual(
            Config.QIANFAN_WEB_SEARCH_PATH, "/v2/ai_search/web_search"
        )
        self.assertEqual(
            Config.QIANFAN_TRENDING_PATH, "/v2/tools/baidu_trending"
        )
        self.assertEqual(Config.QIANFAN_WEB_SEARCH_TOP_K, 50)
        self.assertEqual(Config.QIANFAN_REQUEST_TIMEOUT, 30)


class SentimentConfigContractTest(unittest.TestCase):
    def test_sentiment_configuration_is_available(self):
        self.assertEqual(Config.SENTIMENT_TEXT_LIMIT, 500)
        self.assertEqual(Config.SENTIMENT_ALGORITHM_VERSION, "sentiment-v1")
        self.assertEqual(Config.SENTIMENT_PROMPT_VERSION, "sentiment-prompt-v1")
        self.assertEqual(Config.SENTIMENT_PLATFORM_MIN_ARTICLES, 3)
        self.assertEqual(Config.SNOWNLP_POSITIVE_THRESHOLD, 0.60)
        self.assertEqual(Config.SNOWNLP_NEGATIVE_THRESHOLD, 0.40)


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
