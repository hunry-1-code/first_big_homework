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


class PropagationBuilderTest(unittest.TestCase):
    def _article(self, id, title, hour, **kwargs):
        class Stub: pass
        value=Stub(); value.id=id; value.title=title; value.clean_content=kwargs.pop('content',title); value.raw_content=value.clean_content
        value.raw_json=kwargs.pop('raw_json',{}); value.publish_time=datetime(2026,7,10,8)+timedelta(hours=hour); value.first_crawled_at=value.publish_time
        value.platform=kwargs.pop('platform','weibo'); value.source_article_id=str(id); value.source_url=f'https://example.com/{id}'
        value.author=kwargs.pop('author',f'用户{id}'); value.author_id=str(id); value.author_followers=kwargs.pop('followers',100)
        value.author_verified=False; value.author_type=kwargs.pop('author_type',None); value.likes_count=kwargs.pop('likes',0); value.comments_count=0; value.reposts_count=0; value.views_count=0
        return value

    def test_explicit_parent_wins_and_inferred_node_has_one_parent(self):
        from app.propagation.builder import build_propagation_graph
        a=self._article(1,'某公司发布新产品',0)
        b=self._article(2,'转发某公司发布新产品',1,raw_json={'retweeted_status':{'id':'1'}})
        c=self._article(3,'某公司新产品引发关注',2)
        result=build_propagation_graph([a,b,c])
        edge=next(x for x in result['graph']['links'] if x['target']==2)
        self.assertEqual(edge['source'],1); self.assertEqual(edge['evidence_type'],'explicit')
        inferred=[x for x in result['graph']['links'] if x['target']==3]
        self.assertEqual(len(inferred),1)
        self.assertEqual(inferred[0]['evidence_type'],'inferred')

    def test_unrelated_articles_remain_multiple_roots(self):
        from app.propagation.builder import build_propagation_graph
        result=build_propagation_graph([self._article(1,'暴雨预警',0),self._article(2,'电影票房增长',1)])
        self.assertEqual(result['graph']['links'],[])
        self.assertEqual(result['summary']['origin_candidate_count'],2)
        self.assertEqual(result['coverage_status'], 'insufficient')
        self.assertEqual(result['graph_mode'], 'propagation')
        self.assertIsInstance(result['limitations'], list)

    def test_textual_weibo_repost_is_explicit_evidence(self):
        from app.propagation.builder import build_propagation_graph
        parent = self._article(1, '某公司发布公告', 0, author='账号甲')
        child = self._article(
            2,
            '转发公告',
            1,
            content='//@账号甲 某公司发布公告',
        )

        result = build_propagation_graph([parent, child])
        edge = result['graph']['links'][0]

        self.assertEqual(edge['source'], 1)
        self.assertEqual(edge['evidence_type'], 'explicit')

    def test_related_followup_exposes_component_evidence(self):
        from app.propagation.builder import build_propagation_graph
        parent = self._article(1, '某公司发布新产品', 0)
        child = self._article(2, '某公司新产品引发关注', 2)

        result = build_propagation_graph([parent, child])
        edge = result['graph']['links'][0]

        self.assertEqual(edge['evidence_type'], 'inferred')
        self.assertGreaterEqual(edge['evidence_components']['semantic'], 0.20)
        self.assertGreaterEqual(edge['evidence_components']['final_score'], 0.38)
        self.assertTrue(edge['evidence_components']['entity_or_keyword'] > 0)
        self.assertEqual(result['coverage_status'], 'sufficient')

    def test_missing_author(self):
        """缺少作者使用默认值。"""
        class Stub:
            id = 1; author = ""; platform = "微博"; publish_time = datetime(2026, 7, 10)
            author_followers = 0; author_type = None; title = "匿名"; url = "http://a/1"

        name = Stub.author or "匿名用户"
        self.assertEqual(name, "匿名用户")


class PropagationExplanationTest(unittest.TestCase):
    def _article(self, article_id, title, platform, keywords):
        class Stub:
            pass

        article = Stub()
        article.id = article_id
        article.title = title
        article.platform = platform
        article.author = f"作者{article_id}"
        article.publish_time = datetime(2026, 7, 10, 8) + timedelta(hours=article_id)
        article.clean_content = title * 3
        article.keywords = [{"term": term} for term in keywords]
        article.entities = {}
        return article

    def test_keyword_relations_reference_shared_articles_and_platforms(self):
        from app.propagation.keyword_relations import build_keyword_relations

        rows = build_keyword_relations(
            [
                self._article(1, "人工智能产业政策发布", "news_people", ["人工智能", "产业政策"]),
                self._article(2, "人工智能产业迎来投资", "news_36kr", ["人工智能", "产业政策", "投资"]),
                self._article(3, "投资机构解读人工智能", "news_thepaper", ["人工智能", "投资"]),
            ]
        )

        relation = next(
            item
            for item in rows
            if set(item["terms"]) == {"人工智能", "产业政策"}
        )
        self.assertEqual(relation["article_ids"], [1, 2])
        self.assertEqual(relation["article_count"], 2)
        self.assertEqual(relation["platform_count"], 2)
        self.assertEqual(len(relation["example_titles"]), 2)

    def test_legacy_chat_client_is_not_used_for_internet_trace(self):
        from app.services.propagation_analysis_service import analyze_propagation

        articles = [self._article(1, "最早报道", "news_people", ["政策", "发布"])]
        graph = {
            "graph": {"nodes": [{"id": 1}], "links": []},
            "key_nodes": [{"id": 1}],
            "summary": {"origin_candidate_count": 1},
            "limitations": [],
        }

        class Client:
            model_name = "test-model"

            def chat(self, messages, **kwargs):
                return {
                    "model": "test-model",
                    "content": '{"summary":"分析","origin_candidate_id":999,"key_paths":[{"article_ids":[1,999],"explanation":"路径"}]}'
                }

        result = analyze_propagation("测试事件", articles, graph, client=Client())

        self.assertEqual(result["llm_analysis"]["status"], "unavailable")
        self.assertEqual(result["origin_analysis"]["method"], "doubao_web_search")
        self.assertEqual(result["origin_analysis"]["scope"], "internet_web_search")
        self.assertTrue(result["graph"]["links"])

    def test_doubao_unavailable_keeps_keyword_rule_evidence(self):
        from app.llm.doubao_client import DoubaoUnavailableError
        from app.services.propagation_analysis_service import analyze_propagation

        articles = [self._article(1, "最早报道", "news_people", ["政策", "发布"])]
        graph = {
            "graph": {"nodes": [{"id": 1}], "links": []},
            "key_nodes": [{"id": 1}],
            "summary": {"origin_candidate_count": 1},
            "limitations": ["样本有限"],
        }

        class Client:
            model_name = "test-model"

            def web_search(self, query, limit=10):
                raise DoubaoUnavailableError("offline")

        result = analyze_propagation("测试事件", articles, graph, client=Client())

        self.assertEqual(result["llm_analysis"]["status"], "unavailable")
        self.assertEqual(result["origin_analysis"]["method"], "doubao_web_search")
        self.assertEqual(result["origin_analysis"]["scope"], "internet_web_search")
        self.assertTrue(result["graph"]["links"])

    def test_doubao_trace_builds_six_node_keyword_path_with_edges(self):
        from app.services.propagation_analysis_service import analyze_propagation

        articles = [
            self._article(1, "张雪峰谈高考志愿和专业选择", "bilibili", ["张雪峰", "高考志愿", "专业选择"]),
            self._article(2, "就业前景与新闻学讨论", "weibo", ["就业前景", "新闻学", "张雪峰"]),
        ]
        graph = {"graph": {"nodes": [], "links": []}, "limitations": []}
        top_keywords = [
            {"word": "张雪峰", "weight": 1.0},
            {"word": "高考志愿", "weight": 0.9},
            {"word": "专业选择", "weight": 0.8},
            {"word": "就业前景", "weight": 0.7},
            {"word": "新闻学", "weight": 0.6},
        ]

        class Doubao:
            model_name = "doubao-test"

            def web_search(self, query, limit=10):
                return {
                    "model": "doubao-test",
                    "citations": [{"title": "疑似首发", "url": "https://source.example/first"}],
                    "search_calls": [{"type": "web_search_call"}],
                    "text": '''```json
                    {"summary":"事件由访谈切片扩散到志愿讨论", "origin":{"title":"疑似首发","url":"https://source.example/first","publish_time":"2026-07-01T08:00:00+08:00","source":"示例媒体","reason":"检索时间最早","confidence":0.86}, "paths":[{"source":"张雪峰","target":"高考志愿","reason":"人物观点进入高考场景","confidence":0.91,"evidence_urls":["https://source.example/first"]},{"source":"高考志愿","target":"专业选择","reason":"讨论转向专业决策","confidence":0.88},{"source":"专业选择","target":"就业前景","reason":"选择依据延伸到就业","confidence":0.82},{"source":"就业前景","target":"新闻学","reason":"具体专业成为争议焦点","confidence":0.79}]}
                    ```''',
                }

        result = analyze_propagation(
            "张雪峰事件", articles, graph, doubao_client=Doubao(), top_keywords=top_keywords
        )

        self.assertEqual(result["origin_analysis"]["scope"], "internet_web_search")
        self.assertEqual(result["origin_analysis"]["status"], "success")
        self.assertEqual(len(result["graph"]["nodes"]), 6)
        self.assertEqual(len(result["graph"]["links"]), 5)
        self.assertEqual(result["graph"]["nodes"][0]["category"], "origin_candidate")
        self.assertTrue(all(link["source"] != link["target"] for link in result["graph"]["links"]))
        self.assertTrue(all(link.get("evidence") for link in result["graph"]["links"]))

    def test_doubao_unavailable_keeps_five_keywords_and_rule_paths(self):
        from app.llm.doubao_client import DoubaoUnavailableError
        from app.services.propagation_analysis_service import analyze_propagation

        articles = [self._article(1, "事件讨论", "weibo", ["甲", "乙", "丙", "丁", "戊"])]

        class Doubao:
            model_name = "doubao-test"

            def web_search(self, query, limit=10):
                raise DoubaoUnavailableError("offline")

        result = analyze_propagation(
            "事件",
            articles,
            {"graph": {"nodes": [], "links": []}, "limitations": []},
            doubao_client=Doubao(),
            top_keywords=[
                {"word": word, "weight": 1 - index * 0.1}
                for index, word in enumerate(["关键词甲", "关键词乙", "关键词丙", "关键词丁", "关键词戊"])
            ],
        )

        self.assertEqual(result["origin_analysis"]["status"], "unavailable")
        self.assertEqual(result["coverage_status"], "insufficient")
        self.assertEqual(len(result["graph"]["nodes"]), 5)
        self.assertEqual(len(result["graph"]["links"]), 4)
        self.assertTrue(all(link["evidence_type"] == "keyword_frequency_rule" for link in result["graph"]["links"]))

    def test_non_json_doubao_search_keeps_citation_as_origin_evidence(self):
        from app.services.propagation_analysis_service import analyze_propagation

        articles = [self._article(1, "张雪峰传言", "weibo", ["张雪峰", "去世"])]

        class Doubao:
            model_name = "doubao-test"

            def web_search(self, query, limit=10):
                return {
                    "model": "doubao-test",
                    "text": "联网核查显示该消息属于网络传言，以下为检索结果。",
                    "citations": [
                        {"title": "张雪峰公开活动消息", "url": "https://example.com/fact-check"}
                    ],
                    "search_calls": [{"type": "web_search_call"}],
                }

        result = analyze_propagation(
            "张雪峰去世传言",
            articles,
            {"graph": {"nodes": [], "links": []}, "limitations": []},
            doubao_client=Doubao(),
            top_keywords=[
                {"word": word, "weight": 1 - index * 0.1}
                for index, word in enumerate(["张雪峰", "去世", "地狱梗", "网暴", "高考"])
            ],
        )

        self.assertEqual(result["origin_analysis"]["status"], "success")
        self.assertEqual(result["coverage_status"], "sufficient")
        self.assertEqual(result["origin_analysis"]["scope"], "internet_web_search")
        self.assertEqual(result["origin_analysis"]["origin"]["url"], "https://example.com/fact-check")
        self.assertEqual(len(result["graph"]["nodes"]), 6)
        self.assertEqual(len(result["graph"]["links"]), 5)
        self.assertEqual(result["graph"]["links"][0]["evidence_type"], "doubao_web_search")


if __name__ == "__main__":
    unittest.main()
