from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True, slots=True)
class LifecyclePrediction:
    stage: str
    status: str
    confidence: float
    evidence: dict
    reactivated: bool = False
    momentum: float = 0.0          # -1~1, 正=上升趋势, 负=衰减
    next_stage_hint: str = ""      # 预测下一个阶段


# ── 核心算法：多信号融合生命周期判断 ──

def analyze_lifecycle(
    daily_counts: Sequence[int | float],
    previous_stage: str | None = None,
    *,
    daily_comments: Sequence[int | float] | None = None,
    daily_sentiment_polarity: Sequence[float] | None = None,
    daily_platform_count: Sequence[int | float] | None = None,
) -> LifecyclePrediction:
    """多信号融合生命周期分析。

    信号权重：报道量 40% + 评论量 35% + 情感极化 15% + 平台扩散 10%
    所有信号归一化到 [0,1]（相对事件自身最大值），适应不同规模事件。
    当评论/情感数据缺失时自动回退到纯报道量逻辑。
    """
    counts = _normalized(daily_counts)
    point_count = len(counts)
    total_volume = sum(counts)
    canonical_previous = (
        previous_stage
        if previous_stage in {"潜伏期", "成长期", "高潮期", "消退期"}
        else None
    )

    # 数据不足 → 沿用已有阶段
    if point_count < 3:
        stage = canonical_previous or "潜伏期"
        return LifecyclePrediction(
            stage=stage, status="data_insufficient",
            confidence=min(0.40, 0.10 + point_count * 0.08),
            evidence={"point_count": point_count, "reason": "有效日序列不足"},
            momentum=0.0, next_stage_hint="",
        )

    # ── 构建综合信号 ──
    vol = _norm_to_max(counts)                     # 报道量归一化
    cmt = _norm_to_max(daily_comments) if daily_comments else None
    pol = _norm_to_max(daily_sentiment_polarity) if daily_sentiment_polarity else None
    plat = _norm_to_max(daily_platform_count) if daily_platform_count else None

    # 综合得分：加权融合
    combined = []
    weights_used = {"volume": 0.4, "comments": 0.0, "sentiment": 0.0, "platforms": 0.0}
    for i in range(point_count):
        score = vol[i] * 0.4
        w_total = 0.4
        if cmt and i < len(cmt):
            score += cmt[i] * 0.35
            w_total += 0.35
            weights_used["comments"] = 0.35
        if pol and i < len(pol):
            score += pol[i] * 0.15
            w_total += 0.15
            weights_used["sentiment"] = 0.15
        if plat and i < len(plat):
            score += plat[i] * 0.10
            w_total += 0.10
            weights_used["platforms"] = 0.10
        combined.append(score / w_total)

    peak = max(combined)
    current = combined[-1]
    peak_idx = max(range(point_count), key=combined.__getitem__)
    recent = combined[-min(4, point_count):]
    recent_avg = sum(combined[-3:]) / min(3, point_count)
    slope = _linear_slope(recent)
    norm_slope = slope / max(0.01, peak)
    peak_ratio = current / max(0.01, peak)
    recent_peak_ratio = recent_avg / max(0.01, peak)
    variation = (max(recent) - min(recent)) / max(0.01, peak)

    # ── 动量：综合信号的变化趋势 ──
    if point_count >= 3:
        earlier = sum(combined[-6:-3]) / min(3, max(1, point_count - 3))
        later = sum(combined[-3:]) / min(3, point_count)
        momentum = (later - earlier) / max(0.01, earlier) if earlier > 0 else (0.5 if later > 0 else 0.0)
    else:
        momentum = 0.0
    momentum = round(max(-1.0, min(1.0, momentum)), 4)

    # ── 持续衰减检测 ──
    sustained_decline = (
        point_count >= 4
        and all(combined[-(i+1)] < combined[-(i+2)] for i in range(3))
        and current <= peak * 0.55
    )

    # ── 多因素阶段判断 ──
    # 活动指数：当前综合信号相对于峰值的位置
    activity_index = current / max(0.01, peak)
    # 近期密度：最近 7 天日均 vs 全部日均
    recent_window = min(7, point_count)
    recent_density = sum(combined[-recent_window:]) / recent_window if recent_window > 0 else 0
    all_density = total_volume / point_count if point_count > 0 else 0
    density_ratio = recent_density / max(0.01, all_density)

    # 消退期：历史跨度大 + 绝对活跃度低（不用相对值，长尾事件 d_ratio 会虚高）
    if point_count > 90 and activity_index < 0.3 and recent_density < 0.6:
        stage = "消退期"
        confidence = 0.80
        next_hint = "消退期"
    # 消退期：持续衰减 或 已过峰值且当前 < 峰值×55%
    elif sustained_decline or (peak_idx < point_count - 2 and peak_ratio < 0.55 and momentum < -0.05):
        stage = "消退期"
        confidence = 0.82
        next_hint = "潜伏期" if peak_ratio < 0.25 else "消退期"
    # 潜伏期：信号极低，跨度短，总量少
    elif peak < 0.25 and abs(norm_slope) < 0.06 and point_count < 30:
        stage = "潜伏期"
        confidence = 0.72
        next_hint = "成长期" if momentum > 0.03 else "潜伏期"
    # 高潮期：稳定在高位 + 近期活跃
    elif recent_peak_ratio >= 0.80 and variation < 0.20 and abs(norm_slope) < 0.08:
        stage = "高潮期"
        confidence = 0.78
        next_hint = "消退期" if momentum < -0.03 else "高潮期"
    # 成长期：上升趋势
    elif momentum > 0.03 and current >= combined[0]:
        stage = "成长期"
        confidence = min(0.88, 0.60 + abs(momentum))
        next_hint = "高潮期" if momentum > 0.12 else "成长期"
    # 上升但不强 → 可能是成长期早期
    elif momentum > 0.0:
        stage = "成长期"
        confidence = 0.55
        next_hint = "成长期"
    # 跨度长但绝对密度极低 → 消退期
    elif point_count > 30 and recent_density < 0.3:
        stage = "消退期"
        confidence = 0.60
        next_hint = "消退期"
    # 其他情况：低活跃 → 潜伏期
    else:
        stage = "潜伏期"
        confidence = 0.50
        next_hint = "潜伏期"

    # ── 前一阶段约束（防抖动）──
    if canonical_previous == "高潮期" and stage in {"潜伏期", "成长期"}:
        if momentum > -0.08:
            stage = "高潮期"
            confidence = min(confidence, 0.60)
    elif canonical_previous == "消退期":
        if momentum > 0.08 and peak_ratio > 0.40:
            stage = "成长期"
            confidence = max(confidence, 0.68)
            return LifecyclePrediction(
                stage=stage, status="sufficient", confidence=confidence,
                reactivated=True, momentum=momentum, next_stage_hint=next_hint,
                evidence=_evidence(point_count, total_volume, peak, current, peak_idx,
                                   peak_ratio, recent_peak_ratio, norm_slope, variation,
                                   sustained_decline, weights_used),
            )
        else:
            stage = "消退期"
            confidence = max(confidence, 0.70)
    elif canonical_previous == "成长期" and stage == "潜伏期":
        stage = "成长期"
        confidence = min(confidence, 0.60)

    return LifecyclePrediction(
        stage=stage, status="sufficient",
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        momentum=momentum, next_stage_hint=next_hint,
        evidence=_evidence(point_count, total_volume, peak, current, peak_idx,
                           peak_ratio, recent_peak_ratio, norm_slope, variation,
                           sustained_decline, weights_used),
    )


def _evidence(point_count, total, peak, current, peak_idx,
              peak_ratio, recent_peak_ratio, norm_slope, variation,
              sustained_decline, weights) -> dict:
    return {
        "point_count": point_count,
        "total_volume": round(total, 3),
        "peak": round(peak, 3),
        "current": round(current, 3),
        "peak_index": peak_idx,
        "peak_ratio": round(peak_ratio, 4),
        "recent_peak_ratio": round(recent_peak_ratio, 4),
        "normalized_slope": round(norm_slope, 4),
        "recent_variation": round(variation, 4),
        "sustained_decline": sustained_decline,
        "signal_weights": weights,
    }


# ── 辅助函数 ──

def _normalized(values: Sequence[int | float] | None) -> list[float]:
    if values is None:
        return []
    return [max(0.0, float(v)) for v in values]


def _norm_to_max(values: Sequence[float]) -> list[float]:
    """归一化到 [0, 1]，相对自身最大值。"""
    vals = [float(v) for v in values]
    m = max(vals) if vals else 1.0
    return [v / m if m > 0 else 0.0 for v in vals]


def _linear_slope(values: Sequence[int | float]) -> float:
    numbers = _normalized(values)
    if len(numbers) < 2:
        return 0.0
    x_mean = (len(numbers) - 1) / 2
    y_mean = sum(numbers) / len(numbers)
    denom = sum((i - x_mean) ** 2 for i in range(len(numbers)))
    if denom == 0:
        return 0.0
    return sum((i - x_mean) * (v - y_mean) for i, v in enumerate(numbers)) / denom


# ── 公开 API ──

def predict_lifecycle_stage(daily_counts: list[int], **kwargs) -> str:
    return analyze_lifecycle(daily_counts, **kwargs).stage


def get_lifecycle_change_points(
    daily_counts: Sequence[int | float],
    dates: Sequence[str],
    **kwargs,
) -> list[dict]:
    length = min(len(daily_counts), len(dates))
    if length < 2:
        return []
    points = []
    prev = analyze_lifecycle(list(daily_counts[:1]), **kwargs).stage
    for i in range(1, length):
        cur = analyze_lifecycle(
            list(daily_counts[: i + 1]), previous_stage=prev, **kwargs
        ).stage
        if cur != prev:
            points.append({"date": dates[i], "from_stage": prev, "to_stage": cur, "index": i})
        prev = cur
    return points


__all__ = [
    "LifecyclePrediction",
    "analyze_lifecycle",
    "get_lifecycle_change_points",
    "predict_lifecycle_stage",
]
