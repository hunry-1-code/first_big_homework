import pytest

from app.llm.doubao_client import DoubaoClient, DoubaoUnavailableError


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "model": "doubao-seed-2-1-pro-260628",
            "output": [
                {"type": "web_search_call", "id": "search-1", "action": {"type": "search"}},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "检索完成",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com/source",
                                    "title": "来源标题",
                                }
                            ],
                        }
                    ],
                },
            ],
        }


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def test_doubao_client_calls_responses_api_with_web_search():
    session = FakeSession()
    client = DoubaoClient(
        api_key="ark-secret",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model_name="doubao-seed-2-1-pro-260628",
        session=session,
    )

    result = client.web_search("查询事件来源", limit=6)

    url, kwargs = session.calls[0]
    assert url == "https://ark.cn-beijing.volces.com/api/v3/responses"
    assert kwargs["headers"]["Authorization"] == "Bearer ark-secret"
    assert kwargs["json"]["model"] == "doubao-seed-2-1-pro-260628"
    assert kwargs["json"]["tools"] == [{"type": "web_search", "limit": 6}]
    assert result["text"] == "检索完成"
    assert result["citations"] == [
        {"url": "https://example.com/source", "title": "来源标题"}
    ]


def test_doubao_client_rejects_missing_api_key():
    with pytest.raises(DoubaoUnavailableError):
        DoubaoClient(api_key="").web_search("查询")
