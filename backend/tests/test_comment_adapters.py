import sys
from pathlib import Path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path: sys.path.insert(0, str(BACKEND_ROOT))
from app.crawler.tikhub_comments import TikHubCommentAdapter

class Client:
    def __init__(self): self.calls = []
    def get_json(self, url, **kwargs):
        self.calls.append(kwargs["params"])
        cursor = kwargs["params"]["cursor"]
        if cursor == 0:
            return {"data": {"comments": [{"id": "c1", "text": "需要回应", "user": {"nickname": "用户"}, "digg_count": 3}], "cursor": 10, "has_more": True}}
        return {"data": {"comments": [{"id": "c2", "content": {"message": "第二页"}}], "has_more": False}}

def test_tikhub_comment_adapter_paginates_and_maps_comments():
    client = Client()
    rows = TikHubCommentAdapter("douyin", "key", client=client).fetch("video1", limit=10)
    assert [row.source_comment_id for row in rows] == ["c1", "c2"]
    assert rows[0].author == "用户"
    assert [call["cursor"] for call in client.calls] == [0, 10]

def test_tikhub_comment_adapter_without_key_does_not_request():
    client = Client()
    assert TikHubCommentAdapter("weibo", "", client=client).fetch("mid") == []
    assert client.calls == []

def test_tikhub_comment_adapter_links_sub_replies():
    class ReplyClient:
        def get_json(self, url, **kwargs):
            if "comment_replies" in url:
                return {"data": {"comments": [{"id": "r1", "text": "回复内容"}]}}
            return {"data": {"comments": [{"id": "c1", "text": "一级评论", "reply_count": 1}], "has_more": False}}
    rows = TikHubCommentAdapter("weibo", "key", client=ReplyClient()).fetch("post", limit=5, reply_limit=2)
    assert [row.source_comment_id for row in rows] == ["c1", "r1"]
    assert rows[1].parent_source_comment_id == "c1"
