from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class HotSeedSnapshot:
    seed_id: int
    platform: str
    title: str
    rank: int | None
    snapshot_time: datetime


@dataclass(slots=True)
class ExpansionSeed:
    query: str
    platforms: list[str]
    best_rank: int | None
    source_seed_ids: list[int]
    first_seen_at: datetime
    last_seen_at: datetime
    report_count_contribution: int = 0


def normalize_hot_seed_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = " ".join(text.split()).strip()
    text = re.sub(r"^[#＃]+|[#＃]+$", "", text).strip()
    return text


def merge_hot_seeds(snapshots: list[HotSeedSnapshot]) -> list[ExpansionSeed]:
    groups: dict[str, list[HotSeedSnapshot]] = {}
    for snapshot in snapshots:
        query = normalize_hot_seed_title(snapshot.title)
        if not query:
            continue
        groups.setdefault(query, []).append(snapshot)
    output = []
    for query, rows in groups.items():
        ordered = sorted(rows, key=lambda item: (item.snapshot_time, item.seed_id))
        ranks = [int(item.rank) for item in rows if item.rank is not None]
        output.append(
            ExpansionSeed(
                query=query,
                platforms=sorted({item.platform for item in rows}),
                best_rank=min(ranks) if ranks else None,
                source_seed_ids=sorted({item.seed_id for item in rows}),
                first_seen_at=ordered[0].snapshot_time,
                last_seen_at=ordered[-1].snapshot_time,
            )
        )
    return sorted(
        output,
        key=lambda item: (
            item.best_rank is None,
            item.best_rank if item.best_rank is not None else 10**9,
            -len(item.platforms),
            item.query,
        ),
    )
