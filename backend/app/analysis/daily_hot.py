from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


_BRACKET_MARKS = str.maketrans({
    "【": " ",
    "】": " ",
    "[": " ",
    "]": " ",
    "《": " ",
    "》": " ",
})
_HEAT_SUFFIX = re.compile(
    r"(?:\s*[-|·]?\s*)"
    r"(?:热度|热搜指数|搜索指数)?\s*"
    r"\d+(?:\.\d+)?(?:万|亿)?\s*"
    r"(?:热度|热搜指数|人气)?\s*$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class HotRankItem:
    source: str
    rank: int
    title: str
    source_url: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FusedHotItem:
    normalized_key: str
    normalized_title: str
    fused_score: float
    source_ranks: dict[str, int]
    source_urls: dict[str, str]
    source_payloads: dict[str, dict]
    source_count: int
    best_rank: int


def normalize_hot_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", str(title or ""))
    text = text.translate(_BRACKET_MARKS).replace("#", " ")
    text = _HEAT_SUFFIX.sub("", text)
    text = " ".join(text.split())
    return text.strip(" \t\r\n-—_|·:：,，。!！?？;；'\"")


def _normalized_key(title: str) -> str:
    return re.sub(r"[\W_]+", "", title, flags=re.UNICODE).casefold()


def fuse_hot_rankings(
    items: list[HotRankItem],
    *,
    rrf_k: int = 60,
    limit: int | None = None,
) -> list[FusedHotItem]:
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")
    if limit is not None and limit < 1:
        return []

    grouped: dict[str, dict[str, HotRankItem]] = {}
    titles: dict[str, list[tuple[int, str, str]]] = {}
    for item in items:
        source = str(item.source or "").strip().casefold()
        try:
            rank = int(item.rank)
        except (TypeError, ValueError):
            continue
        normalized_title = normalize_hot_title(item.title)
        key = _normalized_key(normalized_title)
        if not source or rank < 1 or not key:
            continue
        normalized_item = HotRankItem(
            source=source,
            rank=rank,
            title=normalized_title,
            source_url=item.source_url,
            raw=dict(item.raw or {}),
        )
        current = grouped.setdefault(key, {}).get(source)
        if current is None or (rank, normalized_title) < (current.rank, current.title):
            grouped[key][source] = normalized_item
        titles.setdefault(key, []).append((rank, source, normalized_title))

    fused = []
    for key, source_items in grouped.items():
        source_ranks = {
            source: item.rank
            for source, item in sorted(source_items.items())
        }
        source_urls = {
            source: item.source_url
            for source, item in sorted(source_items.items())
            if item.source_url
        }
        source_payloads = {
            source: dict(item.raw or {})
            for source, item in sorted(source_items.items())
        }
        display_title = min(titles[key])[2]
        fused.append(
            FusedHotItem(
                normalized_key=key,
                normalized_title=display_title,
                fused_score=sum(
                    1.0 / (rrf_k + rank) for rank in source_ranks.values()
                ),
                source_ranks=source_ranks,
                source_urls=source_urls,
                source_payloads=source_payloads,
                source_count=len(source_ranks),
                best_rank=min(source_ranks.values()),
            )
        )
    fused.sort(
        key=lambda item: (
            -item.fused_score,
            -item.source_count,
            item.best_rank,
            item.normalized_title,
        )
    )
    return fused[:limit] if limit is not None else fused


__all__ = [
    "FusedHotItem",
    "HotRankItem",
    "fuse_hot_rankings",
    "normalize_hot_title",
]
