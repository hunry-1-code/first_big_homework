from __future__ import annotations


def predict_lifecycle_stage(daily_counts: list[int]) -> str:
    if not daily_counts:
        return "潜伏期"
    if len(daily_counts) >= 2 and daily_counts[-1] > daily_counts[-2]:
        return "成长期"
    return "衰退期"
