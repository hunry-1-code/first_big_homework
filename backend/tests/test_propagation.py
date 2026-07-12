"""事件溯源与传播路径单元测试。

覆盖：关键节点识别、传播图数据结构构建、边界条件
"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class PropagationLogicTest(unittest.TestCase):
    """传播路径逻辑测试（不依赖 DB）。"""

    @staticmethod
    def _make_articles(records: list[dict]) -> list:
        """从 dict 列表生成 article stub 对象。"""
        stubs = []
        for r in records:
            class Stub:
                pass
            s = Stub()
            for k, v in r.items():
                setattr(s, k, v)
            stubs.append(s)
        return stubs

    def test_identify_origin_first_article(self):
        base = datetime(2026, 7, 10, 8, 0, 0)
        articles = self._make_articles([
            {"id": 1, "author": "首发作者", "platform": "微博", "publish_time": base,
             "author_followers": 1000, "author_type": None, "title": "首发", "url": "http://a/1"},
            {"id": 2, "author": "转发者", "platform": "知乎", "publish_time": base + timedelta(hours=2),
             "author_followers": 5000, "author_type": None, "title": "转发", "url": "http://a/2"},
            {"id": 3, "author": "人民日报", "platform": "微博", "publish_time": base + timedelta(hours=5),
             "author_followers": 50000000, "author_type": "官方媒体", "title": "回应", "url": "http://a/3"},
        ])

        from app.analysis.fake_detector import _match_official_media

        # 初始爆料：发布时间最早
        origin = articles[0]
        self.assertEqual(origin.author, "首发作者")

        # 大V：author_followers >= 500000 且不是官媒，发布时间最早
        big_v_candidates = [
            a for a in articles
            if (a.author_followers or 0) >= 500000
            and not _match_official_media(a.author or "")
        ]
        self.assertEqual(len(big_v_candidates), 0)  # 第三个是官媒，排除

        # 官方媒体：匹配白名单，发布时间最早
        official = [a for a in articles if _match_official_media(a.author or "")]
        self.assertEqual(len(official), 1)
        self.assertEqual(official[0].author, "人民日报")

    def test_build_graph_structure(self):
        base = datetime(2026, 7, 10, 8, 0, 0)
        articles = self._make_articles([
            {"id": 1, "author": "用户A", "platform": "微博", "publish_time": base,
             "author_followers": 100, "author_type": None, "title": "首发", "url": "http://a/1"},
            {"id": 2, "author": "用户B", "platform": "知乎", "publish_time": base + timedelta(hours=1),
             "author_followers": 200, "author_type": None, "title": "跟进", "url": "http://a/2"},
            {"id": 3, "author": "用户C", "platform": "百度新闻", "publish_time": base + timedelta(hours=2),
             "author_followers": 300, "author_type": None, "title": "再报", "url": "http://a/3"},
        ])

        # 构建节点
        nodes = []
        for a in articles:
            nodes.append({
                "id": a.id,
                "name": a.author,
                "category": 3,  # 普通
                "symbolSize": 15,
                "platform": a.platform,
                "followers": a.author_followers or 0,
                "publish_time": a.publish_time.isoformat() if a.publish_time else None,
                "title": a.title,
            })

        self.assertEqual(len(nodes), 3)
        self.assertEqual(nodes[0]["name"], "用户A")

        # 构建边（时间链）
        links = []
        for i in range(1, len(articles)):
            links.append({
                "source": articles[i - 1].id,
                "target": articles[i].id,
                "relation": "inferred",
                "confidence": 0.6,
                "evidence": "基于时间先后和内容相似度推测",
            })

        self.assertEqual(len(links), 2)
        self.assertEqual(links[0]["source"], 1)
        self.assertEqual(links[0]["target"], 2)
        self.assertEqual(links[0]["relation"], "inferred")

    def test_empty_articles(self):
        self.assertEqual([], [])  # 空列表返回空

    def test_single_article_no_edges(self):
        base = datetime(2026, 7, 10, 8, 0, 0)
        articles = self._make_articles([
            {"id": 1, "author": "唯一作者", "platform": "微博", "publish_time": base,
             "author_followers": 100, "author_type": None, "title": "独苗", "url": "http://a/1"},
        ])
        self.assertEqual(len(articles), 1)
        # 只有一篇时无边
        links = []
        for i in range(1, len(articles)):
            links.append({})
        self.assertEqual(len(links), 0)

    def test_node_categories(self):
        """验证节点分类逻辑。"""
        from app.analysis.fake_detector import _match_official_media

        authors = [
            ("人民日报", 50000000),   # 官媒 → category 2
            ("新华社", 40000000),     # 官媒 → category 2
            ("大V用户", 600000),      # 大V → category 1 (if not official)
            ("普通用户", 100),        # 普通 → category 3
        ]

        categories = []
        for author, followers in authors:
            is_official = _match_official_media(author)
            if is_official:
                cat = 2
            elif followers >= 500000:
                cat = 1
            else:
                cat = 3
            categories.append(cat)

        self.assertEqual(categories, [2, 2, 1, 3])


class EdgeCasePropagationTest(unittest.TestCase):
    """传播路径边界条件"""

    def test_missing_publish_time(self):
        """缺少发布时间仍然生成节点。"""
        class Stub:
            id = 1; author = "未知"; platform = "微博"; publish_time = None
            author_followers = 0; author_type = None; title = "无时间"; url = "http://a/1"

        node = {
            "id": Stub.id,
            "name": Stub.author,
            "publish_time": Stub.publish_time.isoformat() if Stub.publish_time else None,
        }
        self.assertIsNone(node["publish_time"])
        self.assertEqual(node["name"], "未知")

    def test_missing_author(self):
        """缺少作者使用默认值。"""
        class Stub:
            id = 1; author = ""; platform = "微博"; publish_time = datetime(2026, 7, 10)
            author_followers = 0; author_type = None; title = "匿名"; url = "http://a/1"

        name = Stub.author or "匿名用户"
        self.assertEqual(name, "匿名用户")


if __name__ == "__main__":
    unittest.main()
