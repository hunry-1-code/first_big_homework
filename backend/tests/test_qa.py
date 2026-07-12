import unittest
from datetime import timedelta
from unittest.mock import patch

from app import create_app
from app.extensions import db
from app.models import Article, Event
from app.services.qa_service import answer_question


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    TASK_RECOVER_ON_STARTUP = False
    FRONTEND_ORIGINS = ["http://localhost"]
    JWT_EXPIRES_DELTA = timedelta(hours=1)
    LLM_API_KEY = "test-key"
    LLM_BASE_URL = "https://api.deepseek.com"
    LLM_MODEL_NAME = "deepseek-chat"
    LLM_REQUEST_TIMEOUT = 3


class QAServiceTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        event = Event(title="人工智能监管新规", summary="监管部门发布人工智能治理要求")
        db.session.add(event)
        db.session.flush()
        db.session.add(Article(event_id=event.id, platform="weibo", url="https://e/1", url_hash="qa-1", title="多方回应新规", clean_content="企业和专家对新规作出回应", clean_status="success"))
        db.session.commit()
        self.event_id = event.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    @patch("app.services.qa_service.LLMClient.chat")
    def test_event_question_calls_llm_with_grounded_context(self, chat):
        chat.return_value = {"content": "事件目前处于早期讨论阶段。", "model": "deepseek-v4"}

        result = answer_question(1, "当前发展如何？", self.event_id)

        self.assertEqual(result["method"], "llm")
        self.assertEqual(result["model_name"], "deepseek-v4")
        prompt = chat.call_args.args[0][-1]["content"]
        self.assertIn("人工智能监管新规", prompt)
        self.assertIn("多方回应新规", prompt)

    def test_missing_event_is_rejected(self):
        with self.assertRaises(KeyError):
            answer_question(1, "发生了什么？", 999)

    @patch("app.services.qa_service.LLMClient.chat", side_effect=RuntimeError("offline"))
    def test_llm_failure_returns_explicit_fallback(self, _chat):
        result = answer_question(1, "发生了什么？", self.event_id)
        self.assertEqual(result["method"], "fallback")
        self.assertIn("LLM_UNAVAILABLE", result["warnings"])
        self.assertNotIn("占位", result["answer"])


if __name__ == "__main__":
    unittest.main()
