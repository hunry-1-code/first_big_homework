import unittest

from tools.public_crawl_probe import (
    classify_result,
    extract_visible_text,
    normalize_space,
)


class PublicCrawlProbeTests(unittest.TestCase):
    def test_normalize_space_decodes_entities_and_collapses_whitespace(self):
        self.assertEqual(normalize_space(" 舆情&nbsp;\n  分析\t系统 "), "舆情 分析 系统")

    def test_extract_visible_text_ignores_script_and_style(self):
        html = """
        <html>
          <head><style>.hidden{}</style><script>var token='secret';</script></head>
          <body><h1>热点事件</h1><p>群众反馈明显增加。</p></body>
        </html>
        """.encode("utf-8")

        text = extract_visible_text(html, "text/html; charset=utf-8")

        self.assertIn("热点事件", text)
        self.assertIn("群众反馈明显增加", text)
        self.assertNotIn("secret", text)

    def test_classify_result_marks_verification_page_as_unusable(self):
        ok, classification = classify_result(200, "请先登录后继续访问 安全验证 验证码", "")

        self.assertFalse(ok)
        self.assertEqual(classification, "login_or_verification_required")

    def test_classify_result_does_not_block_page_for_nav_login_text(self):
        text = "百度资讯搜索_舆情 百度首页 登录 搜索工具 百度为您找到相关资讯176个 " * 8

        ok, classification = classify_result(200, text, "")

        self.assertTrue(ok)
        self.assertEqual(classification, "public_content_accessible")

    def test_classify_result_marks_sina_visitor_system_as_limited(self):
        ok, classification = classify_result(200, "Sina Visitor System", "")

        self.assertFalse(ok)
        self.assertEqual(classification, "login_or_verification_required")

    def test_classify_result_marks_empty_search_results_as_unusable(self):
        text = "澎湃新闻 正在搜索 找到约 0 个结果 查看更多 关于澎湃 " * 4

        ok, classification = classify_result(200, text, "")

        self.assertFalse(ok)
        self.assertEqual(classification, "no_search_results")

    def test_classify_result_marks_public_content_as_accessible(self):
        text = "舆情事件 " * 80

        ok, classification = classify_result(200, text, "")

        self.assertTrue(ok)
        self.assertEqual(classification, "public_content_accessible")

    def test_classify_result_marks_403_as_blocked(self):
        ok, classification = classify_result(403, "Forbidden", "HTTP Error 403")

        self.assertFalse(ok)
        self.assertEqual(classification, "blocked_or_rate_limited")


if __name__ == "__main__":
    unittest.main()
