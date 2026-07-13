import json
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis.llm_keywords import (
    _merge_llm_keywords,
    _parse_batch_response,
    extract_keywords_llm,
)
from app.analysis.result import AnalysisDocument, ArticleKeyword


def _document(article_id: int) -> AnalysisDocument:
    return AnalysisDocument(
        article_id=article_id,
        snapshot_id=None,
        content_version=1,
        title=f"第{article_id}篇重庆暴雨救援进展",
        title_tokens=["重庆", "暴雨", "救援"],
        body_tokens=["重庆", "暴雨", "导致", "道路", "积水", "应急", "救援"],
        platform="weibo",
    )


def _valid_keywords(prefix: str):
    return [
        {
            "term": f"{prefix}关键词{index}",
            "score": 0.9 - index * 0.1,
            "sentiment": "neutral",
            "entity_type": "event",
        }
        for index in range(3)
    ]


class LLMKeywordParserTest(unittest.TestCase):
    def test_parser_accepts_only_requested_ids_and_valid_items(self):
        content = json.dumps(
            {
                "1": [
                    {
                        "term": "重庆暴雨",
                        "score": 1.4,
                        "sentiment": "negative",
                        "entity_type": "event",
                    },
                    {"term": "", "score": 0.5},
                    "invalid",
                ],
                "2": _valid_keywords("第二篇"),
                "999": _valid_keywords("越界"),
            },
            ensure_ascii=False,
        )

        parsed = _parse_batch_response(content, allowed_ids={1, 2}, max_per_doc=8)

        self.assertEqual(set(parsed), {1, 2})
        self.assertEqual(len(parsed[1]), 1)
        self.assertEqual(parsed[1][0]["score"], 1.0)
        self.assertEqual(parsed[1][0]["source"], "llm")
        self.assertNotIn(999, parsed)


class LLMKeywordBatchingTest(unittest.TestCase):
    def test_batches_requests_and_keeps_partial_results(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def chat(self, messages, **kwargs):
                payload = json.loads(messages[-1]["content"])
                self.calls.append(payload)
                first_id = payload[0]["article_id"]
                return {
                    "content": json.dumps(
                        {str(first_id): _valid_keywords(f"文章{first_id}")},
                        ensure_ascii=False,
                    )
                }

        client = FakeClient()
        documents = [_document(article_id) for article_id in range(1, 7)]

        result = extract_keywords_llm(
            documents,
            client=client,
            batch_size=2,
        )

        self.assertEqual(len(client.calls), 3)
        self.assertTrue(all(len(batch) <= 2 for batch in client.calls))
        self.assertEqual(set(result), {1, 3, 5})

    def test_missing_or_short_llm_result_uses_tfidf_fallback(self):
        tfidf = {
            1: [ArticleKeyword("规则词一", 0.9, 1, "tfidf", "word")],
            2: [ArticleKeyword("规则词二", 0.8, 1, "tfidf", "word")],
        }
        llm = {1: _valid_keywords("模型")}

        merged = _merge_llm_keywords(llm, tfidf)

        self.assertEqual(merged[1][0]["source"], "llm")
        self.assertEqual(merged[2][0]["term"], "规则词二")
        self.assertEqual(merged[2][0]["source"], "tfidf")
        self.assertEqual(merged[2][0]["sentiment"], "neutral")


if __name__ == "__main__":
    unittest.main()
