from app.analysis.sentiment_analyzer import analyze_comments_batch


class JsonClient:
    def __init__(self, content):
        self.content = content

    def chat(self, *_args, **_kwargs):
        return {"content": self.content}


class FailingClient:
    def chat(self, *_args, **_kwargs):
        raise TimeoutError("llm timeout")


def test_batch_uses_llm_rows_and_falls_back_for_missing_ids(monkeypatch):
    monkeypatch.setattr(
        "app.analysis.sentiment_analyzer.analyze_with_snownlp",
        lambda text: {"label": "neutral", "score": 0.0},
    )
    result = analyze_comments_batch(
        [{"id": 1, "text": "支持"}, {"id": 2, "text": "仍需观察"}],
        client=JsonClient('[{"id":1,"label":"positive","reason":"表示支持"}]'),
    )

    assert result[1]["method"] == "llm_batch"
    assert result[1]["label"] == "positive"
    assert result[2]["method"] == "snownlp_fallback"


def test_batch_falls_back_for_every_comment_when_llm_fails(monkeypatch):
    monkeypatch.setattr(
        "app.analysis.sentiment_analyzer.analyze_with_snownlp",
        lambda text: {"label": "negative", "score": -0.4},
    )
    result = analyze_comments_batch(
        [{"id": 7, "text": "质疑"}, {"id": 8, "text": "不满意"}],
        client=FailingClient(),
    )

    assert set(result) == {7, 8}
    assert {row["method"] for row in result.values()} == {"snownlp_fallback"}
