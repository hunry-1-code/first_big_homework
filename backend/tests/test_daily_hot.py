import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis.daily_hot import HotRankItem, fuse_hot_rankings, normalize_hot_title


class DailyHotNormalizationTest(unittest.TestCase):
    def test_normalizes_unicode_hashtags_whitespace_and_heat_suffix(self):
        self.assertEqual(
            normalize_hot_title("  ＃某地  暴雨＃  123万热度 "),
            "某地 暴雨",
        )

    def test_keeps_meaningful_internal_punctuation_but_drops_outer_marks(self):
        self.assertEqual(normalize_hot_title("【政策发布】A股、港股联动"), "政策发布 A股、港股联动")


class DailyHotFusionTest(unittest.TestCase):
    def test_merges_same_title_and_sums_independent_source_rrf(self):
        ranked = fuse_hot_rankings(
            [
                HotRankItem("weibo_hot", 1, "#某地暴雨#"),
                HotRankItem("baidu_hot", 3, "某地暴雨"),
                HotRankItem("zhihu_hot", 1, "另一事件"),
            ],
            rrf_k=60,
        )

        self.assertEqual(ranked[0].normalized_title, "某地暴雨")
        self.assertEqual(ranked[0].source_ranks, {"weibo_hot": 1, "baidu_hot": 3})
        self.assertAlmostEqual(ranked[0].fused_score, 1 / 61 + 1 / 63)

    def test_same_source_contributes_only_its_best_rank(self):
        ranked = fuse_hot_rankings(
            [
                HotRankItem("weibo_hot", 8, "同一热点"),
                HotRankItem("weibo_hot", 2, "#同一热点#"),
                HotRankItem("baidu_hot", 10, "同一热点"),
            ],
            rrf_k=60,
        )

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].source_ranks, {"weibo_hot": 2, "baidu_hot": 10})
        self.assertAlmostEqual(ranked[0].fused_score, 1 / 62 + 1 / 70)

    def test_sorting_is_stable_and_limit_is_applied(self):
        ranked = fuse_hot_rankings(
            [
                HotRankItem("weibo_hot", 1, "B事件"),
                HotRankItem("baidu_hot", 1, "A事件"),
                HotRankItem("zhihu_hot", 2, "C事件"),
            ],
            rrf_k=60,
            limit=2,
        )

        self.assertEqual([item.normalized_title for item in ranked], ["A事件", "B事件"])

    def test_invalid_rows_are_ignored(self):
        ranked = fuse_hot_rankings(
            [
                HotRankItem("weibo_hot", 0, "无效名次"),
                HotRankItem("", 1, "无来源"),
                HotRankItem("baidu_hot", 1, "###"),
                HotRankItem("zhihu_hot", 2, "有效事件"),
            ]
        )

        self.assertEqual([item.normalized_title for item in ranked], ["有效事件"])


if __name__ == "__main__":
    unittest.main()
