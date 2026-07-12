"""趋势预测（生命周期判定）单元测试。

覆盖：潜伏期/成长期/高潮期/衰退期判定 + 阶段切换点 + 滑动窗口平滑 + 边界条件
"""
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis.trend_predictor import (
    LATENT_MAX_DAILY,
    LATENT_MAX_TOTAL,
    WINDOW_SIZE,
    _growth_rate,
    _smooth,
    get_lifecycle_change_points,
    predict_lifecycle_stage,
)


class SmoothTest(unittest.TestCase):
    """滑动窗口均值平滑测试"""

    def test_single_value(self):
        self.assertEqual(_smooth([10]), [10.0])

    def test_window_smoothing(self):
        result = _smooth([1, 5, 10], window=3)
        self.assertEqual(len(result), 3)
        # 中间点应为 (1+5+10)/3 = 5.33...
        self.assertAlmostEqual(result[1], 16 / 3, places=4)

    def test_window_size_one_no_smoothing(self):
        self.assertEqual(_smooth([1, 5, 10], window=1), [1.0, 5.0, 10.0])


class GrowthRateTest(unittest.TestCase):
    """日增长率计算测试"""

    def test_first_is_zero(self):
        rates = _growth_rate([10.0, 20.0, 30.0])
        self.assertEqual(rates[0], 0.0)

    def test_positive_growth(self):
        rates = _growth_rate([10.0, 20.0])
        self.assertEqual(rates[1], 1.0)  # 100% growth

    def test_negative_growth(self):
        rates = _growth_rate([20.0, 10.0])
        self.assertEqual(rates[1], -0.5)

    def test_zero_prev_positive_current(self):
        rates = _growth_rate([0.0, 5.0])
        self.assertEqual(rates[1], 1.0)


class LifecycleStageTest(unittest.TestCase):
    """生命周期阶段判定测试"""

    def test_empty_returns_latent(self):
        self.assertEqual(predict_lifecycle_stage([]), "潜伏期")

    def test_latent_low_counts(self):
        counts = [3, 4, 5, 3, 5]
        self.assertEqual(predict_lifecycle_stage(counts), "潜伏期")

    def test_growth_sustained_rise(self):
        counts = [5, 15, 30, 50, 80, 120]
        self.assertEqual(predict_lifecycle_stage(counts), "成长期")

    def test_peak_stable_high(self):
        counts = [80, 100, 120, 115, 118, 116, 114]
        self.assertEqual(predict_lifecycle_stage(counts), "高潮期")

    def test_decline_from_peak(self):
        counts = [120, 115, 110, 105, 100, 50, 40]
        self.assertEqual(predict_lifecycle_stage(counts), "衰退期")

    def test_decline_three_consecutive_days(self):
        counts = [130, 120, 115, 110, 100, 80, 60, 50, 45, 40]
        self.assertEqual(predict_lifecycle_stage(counts), "衰退期")


class LifecycleChangePointsTest(unittest.TestCase):
    """阶段切换点测试"""

    def test_empty_returns_empty(self):
        self.assertEqual(get_lifecycle_change_points([], []), [])

    def test_single_point_no_change(self):
        self.assertEqual(get_lifecycle_change_points([1], ["day1"]), [])

    def test_transition_detected(self):
        counts = [5, 15, 30, 50, 80, 120]
        dates = ["d1", "d2", "d3", "d4", "d5", "d6"]
        points = get_lifecycle_change_points(counts, dates)
        self.assertGreater(len(points), 0)


class ConfigThresholdsTest(unittest.TestCase):
    """确认阈值常量可导入且类型正确"""

    def test_thresholds_defined(self):
        self.assertIsInstance(LATENT_MAX_DAILY, int)
        self.assertIsInstance(LATENT_MAX_TOTAL, int)
        self.assertIsInstance(WINDOW_SIZE, int)


if __name__ == "__main__":
    unittest.main()
