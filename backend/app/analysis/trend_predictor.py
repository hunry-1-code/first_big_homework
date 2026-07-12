from __future__ import annotations

from collections.abc import Sequence


WINDOW_SIZE = 3
LATENT_MAX_DAILY = 3        # 潜伏期：单日 ≤3 篇
LATENT_MAX_TOTAL = 10        # 潜伏期：总量 ≤10 篇
PEAK_TO_GROWTH_RATIO = 3.0   # 峰值 > 潜伏阈值 ×3 才算进入成长期
GROWTH_RATE_MIN = 0.30
PEAK_STABLE_RATE = 0.15
DECLINE_FROM_PEAK = 0.50     # 当前值 < 峰值 ×0.5 → 消退期
DECLINE_CONSECUTIVE_DAYS = 3


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


def _has_sustained_decline(values: Sequence[float]) -> bool:
    if len(values) < DECLINE_CONSECUTIVE_DAYS + 1:
        return False
    recent = values[-(DECLINE_CONSECUTIVE_DAYS + 1) :]
    is_decreasing = all(current < previous for previous, current in zip(recent, recent[1:]))
    meaningful_drop = recent[-1] <= recent[0] * (1.0 - PEAK_STABLE_RATE)
    return is_decreasing and meaningful_drop


def predict_lifecycle_stage(daily_counts: list[int]) -> str:
    counts = _normalized(daily_counts)
    if not counts:
        return "潜伏期"

    smoothed = _smooth(counts)
    current = smoothed[-1]
    peak = max(smoothed)
    total = sum(counts)

    # 潜伏期：数据量极小
    if max(counts) <= LATENT_MAX_DAILY and total <= LATENT_MAX_TOTAL:
        return "潜伏期"

    # 消退期：当前值明显低于峰值
    if peak > 0 and current <= peak * (1.0 - DECLINE_FROM_PEAK):
        return "消退期"
    if _has_sustained_decline(smoothed):
        return "消退期"

    rates = _growth_rate(smoothed)
    recent_rates = rates[-3:] if len(rates) >= 3 else rates
    positive_recent = [rate for rate in recent_rates if rate > 0]
    is_currently_rising = len(counts) >= 2 and counts[-1] > counts[-2]

    # 成长期：快速上升中
    if is_currently_rising:
        if positive_recent and (max(positive_recent) >= GROWTH_RATE_MIN or len(positive_recent) >= 2):
            return "成长期"
    if peak > LATENT_MAX_DAILY * PEAK_TO_GROWTH_RATIO and total > LATENT_MAX_TOTAL and current >= peak * 0.4:
        return "成长期"

    # 高潮期：高位稳定或接近峰值
    near_peak = peak > 0 and current >= peak * (1.0 - PEAK_STABLE_RATE)
    stable = len(recent_rates) >= 2 and all(abs(rate) <= PEAK_STABLE_RATE for rate in recent_rates)
    if near_peak or stable:
        return "高潮期"

    return "成长期"


def get_lifecycle_change_points(
    daily_counts: Sequence[int | float], dates: Sequence[str]
) -> list[dict]:
    length = min(len(daily_counts), len(dates))
    if length < 2:
        return []
    points = []
    previous_stage = predict_lifecycle_stage(list(daily_counts[:1]))
    for index in range(1, length):
        current_stage = predict_lifecycle_stage(list(daily_counts[: index + 1]))
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
