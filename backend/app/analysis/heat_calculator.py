from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean
from typing import Iterable

from app.analysis.hotspot_config import HotspotConfig


@dataclass(slots=True)
class HeatArticle:
    article_id: int
    platform: str
    publish_time: datetime | None = None
    observed_at: datetime | None = None
    is_representative: bool = True
    comments_count: int | None = None
    reposts_count: int | None = None
    likes_count: int | None = None
    views_count: int | None = None
    duplicate_weight: float = 1.0
    spam_weight: float = 1.0

    @property
    def effective_time(self) -> datetime | None:
        return self.publish_time or self.observed_at


@dataclass(slots=True)
class EventHeatInput:
    event_id: int
    articles: list[HeatArticle]
    hotlist_ranks: list[int] = field(default_factory=list)


@dataclass(slots=True)
class EventHeatResult:
    event_id: int
    raw_statistics: dict
    component_scores: dict
    core_heat: float
    spread_heat: float | None
    final_heat: float
    eligible_as_hot: bool
    rank: int | None
    time_confidence: str
    latest_activity_time: datetime | None
    warnings: list[str] = field(default_factory=list)


def _percentile_scores(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    if len(values) == 1:
        return {next(iter(values)): 50.0}
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    output = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_position = (index + end - 1) / 2
        score = average_position / (len(ordered) - 1) * 100
        for current in range(index, end):
            output[ordered[current][0]] = round(score, 6)
        index = end
    return output


def _freshness(hours: float, half_life_hours: int) -> float:
    return max(
        0.0,
        min(100.0, 100 * math.exp(-math.log(2) * max(0.0, hours) / half_life_hours)),
    )


def _time_confidence(representatives: list[HeatArticle]) -> str:
    if not representatives:
        return "low"
    ratio = sum(article.publish_time is not None for article in representatives) / len(
        representatives
    )
    if ratio >= 0.8:
        return "high"
    if ratio >= 0.5:
        return "medium"
    return "low"


def _engagement_percentiles(events: Iterable[EventHeatInput]) -> dict[tuple[int, str], float]:
    by_platform_metric: dict[tuple[str, str], dict[int, float]] = {}
    article_keys = {}
    for event in events:
        for article in event.articles:
            article_keys[article.article_id] = event.event_id
            for metric in (
                "comments_count",
                "reposts_count",
                "likes_count",
                "views_count",
            ):
                value = getattr(article, metric)
                if value is None:
                    continue
                by_platform_metric.setdefault((article.platform, metric), {})[
                    article.article_id
                ] = math.log1p(max(0, int(value)))
    scores = {}
    for (_platform, metric), values in by_platform_metric.items():
        for article_id, score in _percentile_scores(values).items():
            scores[(article_id, metric)] = score
    return scores


def calculate_event_heats(
    events: list[EventHeatInput],
    *,
    calculated_at: datetime,
    config: HotspotConfig,
) -> list[EventHeatResult]:
    if not events:
        return []
    window_start = calculated_at - timedelta(days=config.window_days)
    current_start = calculated_at - timedelta(hours=24)
    previous_start = calculated_at - timedelta(hours=48)
    engagement_scores = _engagement_percentiles(events)
    interim = {}
    report_values = {}
    growth_values = {}
    platform_values = {}
    spread_raw_values = {}

    for event in events:
        representatives = [
            article
            for article in event.articles
            if article.is_representative
            and article.effective_time is not None
            and window_start <= article.effective_time <= calculated_at
        ]
        current_count = sum(
            article.effective_time >= current_start for article in representatives
        )
        previous_count = sum(
            previous_start <= article.effective_time < current_start
            for article in representatives
        )
        growth_rate = (current_count - previous_count) / max(previous_count, 1)
        platforms = {article.platform for article in representatives if article.platform}
        effective_times = [
            article.effective_time
            for article in event.articles
            if article.effective_time is not None
            and window_start <= article.effective_time <= calculated_at
        ]
        latest_activity = max(effective_times, default=None)
        hours_since_activity = (
            (calculated_at - latest_activity).total_seconds() / 3600
            if latest_activity is not None
            else config.window_days * 24
        )
        article_spread = []
        for article in event.articles:
            signals = [
                engagement_scores[(article.article_id, metric)]
                for metric in (
                    "comments_count",
                    "reposts_count",
                    "likes_count",
                    "views_count",
                )
                if (article.article_id, metric) in engagement_scores
            ]
            if not signals:
                continue
            article_time = article.effective_time or calculated_at
            decay = _freshness(
                (calculated_at - article_time).total_seconds() / 3600,
                config.half_life_hours,
            ) / 100
            article_spread.append(
                mean(signals)
                * decay
                * max(0.0, float(article.duplicate_weight or 0))
                * max(0.0, float(article.spam_weight or 0))
            )
        hotlist_scores = [
            max(0.0, 100.0 - (max(1, int(rank)) - 1) * 5.0)
            for rank in event.hotlist_ranks
        ]
        spread_raw = (
            sum(article_spread) + (mean(hotlist_scores) if hotlist_scores else 0.0)
            if article_spread or hotlist_scores
            else None
        )
        raw = {
            "independent_report_count_7d": len(representatives),
            "independent_report_count_24h": current_count,
            "independent_report_count_previous_24h": previous_count,
            "report_growth_rate": round(growth_rate, 6),
            "platform_count": len(platforms),
            "observed_time_count": sum(
                article.publish_time is None and article.observed_at is not None
                for article in representatives
            ),
            "hotlist_platform_count": len(event.hotlist_ranks),
            "best_hotlist_rank": min(event.hotlist_ranks, default=None),
            "latest_activity_time": latest_activity.isoformat()
            if latest_activity
            else None,
            "spread_raw": round(spread_raw, 6) if spread_raw is not None else None,
        }
        interim[event.event_id] = {
            "event": event,
            "raw": raw,
            "latest_activity": latest_activity,
            "hours_since_activity": hours_since_activity,
            "time_confidence": _time_confidence(representatives),
            "spread_raw": spread_raw,
        }
        report_values[event.event_id] = float(len(representatives))
        growth_values[event.event_id] = float(growth_rate)
        platform_values[event.event_id] = float(len(platforms))
        if spread_raw is not None:
            spread_raw_values[event.event_id] = float(spread_raw)

    report_scores = _percentile_scores(report_values)
    growth_scores = _percentile_scores(growth_values)
    platform_scores = _percentile_scores(platform_values)
    spread_scores = _percentile_scores(spread_raw_values)
    results = []
    for event_id, data in interim.items():
        freshness_score = _freshness(
            data["hours_since_activity"], config.half_life_hours
        )
        components = {
            "report_count_score": report_scores[event_id],
            "report_growth_score": growth_scores[event_id],
            "platform_coverage_score": platform_scores[event_id],
            "freshness_score": round(freshness_score, 6),
        }
        core_heat = round(mean(components.values()), 6)
        spread_heat = spread_scores.get(event_id)
        warnings = []
        if spread_heat is None:
            final_heat = core_heat
            warnings.append("SPREAD_DATA_UNAVAILABLE")
        else:
            final_heat = round(
                config.core_weight * core_heat
                + config.spread_weight * spread_heat,
                6,
            )
        raw = data["raw"]
        recent = (
            data["latest_activity"] is not None
            and data["latest_activity"] >= calculated_at
            - timedelta(hours=config.recent_activity_hours)
        )
        eligible = (
            raw["independent_report_count_7d"] >= config.minimum_reports
            and (
                raw["platform_count"] >= config.minimum_platforms
                or bool(data["event"].hotlist_ranks)
            )
            and recent
        )
        results.append(
            EventHeatResult(
                event_id=event_id,
                raw_statistics=raw,
                component_scores=components,
                core_heat=core_heat,
                spread_heat=spread_heat,
                final_heat=final_heat,
                eligible_as_hot=eligible,
                rank=None,
                time_confidence=data["time_confidence"],
                latest_activity_time=data["latest_activity"],
                warnings=warnings,
            )
        )

    ranked = sorted(
        [item for item in results if item.eligible_as_hot],
        key=lambda item: (-item.final_heat, item.event_id),
    )[: config.ranking_limit]
    for rank, item in enumerate(ranked, start=1):
        item.rank = rank
    return results


def calculate_single_event_heat(
    event: EventHeatInput,
    *,
    calculated_at: datetime,
    config: HotspotConfig,
) -> EventHeatResult:
    """Reuse the versioned heat formula for an event outside a HotspotRun."""
    return calculate_event_heats(
        [event],
        calculated_at=calculated_at,
        config=config,
    )[0]
