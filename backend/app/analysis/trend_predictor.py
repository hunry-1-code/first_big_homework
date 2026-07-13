from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


WINDOW_SIZE = 3
LATENT_MAX_DAILY = 3        # 潜伏期：单日 ≤3 篇
LATENT_MAX_TOTAL = 10        # 潜伏期：总量 ≤10 篇
PEAK_TO_GROWTH_RATIO = 3.0   # 峰值 > 潜伏阈值 ×3 才算进入成长期
GROWTH_RATE_MIN = 0.30
PEAK_STABLE_RATE = 0.15
DECLINE_FROM_PEAK = 0.50     # 当前值 < 峰值 ×0.5 → 消退期
DECLINE_CONSECUTIVE_DAYS = 3


@dataclass(frozen=True, slots=True)
class LifecyclePrediction:
    stage: str
    status: str
    confidence: float
    evidence: dict
    reactivated: bool = False


def analyze_lifecycle(
    daily_counts: Sequence[int | float], previous_stage: str | None = None
) -> LifecyclePrediction:
    counts = _normalized(daily_counts)
    canonical_previous = (
        previous_stage
        if previous_stage in {"潜伏期", "成长期", "高潮期", "消退期"}
        else None
    )
    point_count = len(counts)
    total = sum(counts)
    if point_count < 4:
        stage = canonical_previous or "潜伏期"
        return LifecyclePrediction(
            stage=stage,
            status="data_insufficient",
            confidence=min(0.45, 0.15 + point_count * 0.08),
            evidence={
                "point_count": point_count,
                "total_count": total,
                "minimum_points": 4,
                "reason": "有效日序列不足，沿用已有阶段或潜伏期",
            },
        )

    peak = max(counts)
    current = counts[-1]
    peak_index = max(range(point_count), key=counts.__getitem__)
    recent = counts[-min(4, point_count) :]
    recent_average = sum(counts[-3:]) / min(3, point_count)
    recent_slope = _linear_slope(recent)
    normalized_slope = recent_slope / max(1.0, peak)
    peak_ratio = current / peak if peak else 0.0
    recent_peak_ratio = recent_average / peak if peak else 0.0
    recent_variation = (max(recent) - min(recent)) / max(1.0, peak)
    sustained_decline = _has_sustained_decline(counts)
    fallen_from_peak = (
        peak > 0
        and peak_index < point_count - 2
        and current <= peak * (1.0 - DECLINE_FROM_PEAK)
    )
    reactivated = (
        len(counts) >= 3
        and counts[-3] < counts[-2] < counts[-1]
        and normalized_slope >= 0.08
        and peak_ratio >= 0.50
    )
    low_volume = peak <= 5 and total <= max(25.0, point_count * 5.0)
    stable_near_peak = (
        recent_peak_ratio >= 0.85
        and recent_variation <= 0.20
        and abs(normalized_slope) <= 0.08
    )

    if sustained_decline or fallen_from_peak:
        stage = "消退期"
        confidence = 0.82
    elif low_volume:
        stage = "潜伏期"
        confidence = 0.68
    elif stable_near_peak:
        stage = "高潮期"
        confidence = 0.78
    elif normalized_slope > 0.05 and current >= counts[0]:
        stage = "成长期"
        confidence = min(0.90, 0.62 + normalized_slope)
    elif peak <= LATENT_MAX_DAILY * PEAK_TO_GROWTH_RATIO:
        stage = "潜伏期"
        confidence = 0.56
    else:
        stage = "成长期"
        confidence = 0.55

    if canonical_previous == "高潮期" and stage in {"潜伏期", "成长期"}:
        stage = "高潮期"
        confidence = min(confidence, 0.60)
    elif canonical_previous == "消退期":
        if reactivated:
            stage = "成长期"
            confidence = max(confidence, 0.72)
        else:
            stage = "消退期"
            confidence = max(confidence, 0.70)
    elif canonical_previous == "成长期" and stage == "潜伏期":
        stage = "成长期"
        confidence = min(confidence, 0.60)

    return LifecyclePrediction(
        stage=stage,
        status="sufficient",
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        reactivated=bool(canonical_previous == "消退期" and reactivated),
        evidence={
            "point_count": point_count,
            "total_count": round(total, 3),
            "peak": round(peak, 3),
            "current": round(current, 3),
            "peak_index": peak_index,
            "peak_ratio": round(peak_ratio, 6),
            "recent_peak_ratio": round(recent_peak_ratio, 6),
            "normalized_recent_slope": round(normalized_slope, 6),
            "recent_variation": round(recent_variation, 6),
            "sustained_decline": sustained_decline,
            "low_volume": low_volume,
        },
    )


def _normalized(values: Sequence[int | float]) -> list[float]:
    return [max(0.0, float(value)) for value in values]


def _smooth(values: Sequence[int | float], window: int = WINDOW_SIZE) -> list[float]:
    numbers = _normalized(values)
    if not numbers:
        return []
    window = max(1, int(window))
    if window == 1:
        return numbers
    radius = window // 2
    smoothed = []
    for index in range(len(numbers)):
        start = max(0, index - radius)
        end = min(len(numbers), index + radius + 1)
        chunk = numbers[start:end]
        smoothed.append(sum(chunk) / len(chunk))
    return smoothed


def _growth_rate(values: Sequence[int | float]) -> list[float]:
    numbers = _normalized(values)
    if not numbers:
        return []
    rates = [0.0]
    for previous, current in zip(numbers, numbers[1:]):
        if previous == 0:
            rates.append(1.0 if current > 0 else 0.0)
        else:
            rates.append((current - previous) / previous)
    return rates


def _linear_slope(values: Sequence[int | float]) -> float:
    numbers = _normalized(values)
    if len(numbers) < 2:
        return 0.0
    x_mean = (len(numbers) - 1) / 2
    y_mean = sum(numbers) / len(numbers)
    denominator = sum((index - x_mean) ** 2 for index in range(len(numbers)))
    if denominator == 0:
        return 0.0
    return sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(numbers)
    ) / denominator


def _has_sustained_decline(values: Sequence[float]) -> bool:
    if len(values) < DECLINE_CONSECUTIVE_DAYS + 1:
        return False
    recent = values[-(DECLINE_CONSECUTIVE_DAYS + 1) :]
    is_decreasing = all(current < previous for previous, current in zip(recent, recent[1:]))
    meaningful_drop = recent[-1] <= recent[0] * (1.0 - PEAK_STABLE_RATE)
    return is_decreasing and meaningful_drop


def predict_lifecycle_stage(daily_counts: list[int]) -> str:
    return analyze_lifecycle(daily_counts).stage


def get_lifecycle_change_points(
    daily_counts: Sequence[int | float], dates: Sequence[str]
) -> list[dict]:
    length = min(len(daily_counts), len(dates))
    if length < 2:
        return []
    points = []
    previous_stage = analyze_lifecycle(list(daily_counts[:1])).stage
    for index in range(1, length):
        current_stage = analyze_lifecycle(
            list(daily_counts[: index + 1]), previous_stage=previous_stage
        ).stage
        if current_stage != previous_stage:
            points.append(
                {
                    "date": dates[index],
                    "from_stage": previous_stage,
                    "to_stage": current_stage,
                    "index": index,
                }
            )
        previous_stage = current_stage
    return points
