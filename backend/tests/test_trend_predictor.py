from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis.trend_predictor import (
    analyze_lifecycle,
    get_lifecycle_change_points,
    predict_lifecycle_stage,
)


def test_short_series_is_explicitly_insufficient():
    prediction = analyze_lifecycle([1, 2])

    assert prediction.stage == "潜伏期"
    assert prediction.status == "data_insufficient"
    assert prediction.confidence < 0.5
    assert prediction.evidence["point_count"] == 2


def test_growth_peak_and_decline_patterns():
    assert predict_lifecycle_stage([5, 15, 30, 50, 80, 120]) == "成长期"
    assert predict_lifecycle_stage([80, 100, 120, 115, 118, 116, 114]) == "高潮期"
    assert predict_lifecycle_stage([120, 115, 110, 105, 100, 50, 40]) == "消退期"


def test_multi_signal_prediction_records_weights_and_momentum():
    prediction = analyze_lifecycle(
        [5, 8, 12, 20, 30],
        daily_comments=[2, 5, 20, 40, 80],
        daily_sentiment_polarity=[0.1, 0.15, 0.3, 0.5, 0.7],
        daily_platform_count=[1, 1, 2, 3, 4],
    )

    assert prediction.stage == "成长期"
    assert prediction.momentum > 0
    assert prediction.next_stage_hint in {"成长期", "高潮期"}
    assert prediction.evidence["signal_weights"] == {
        "volume": 0.4,
        "comments": 0.35,
        "sentiment": 0.15,
        "platforms": 0.1,
    }


def test_declining_event_can_reactivate_after_clear_recent_rebound():
    prediction = analyze_lifecycle(
        [120, 90, 50, 20, 30, 55, 95],
        previous_stage="消退期",
    )

    assert prediction.stage == "成长期"
    assert prediction.reactivated is True
    assert prediction.momentum > 0.08


def test_change_points_use_public_api_without_removed_helpers():
    points = get_lifecycle_change_points(
        [2, 4, 10, 25, 50, 45, 20],
        ["d1", "d2", "d3", "d4", "d5", "d6", "d7"],
    )

    assert isinstance(points, list)
    assert all(set(item) == {"date", "from_stage", "to_stage", "index"} for item in points)
