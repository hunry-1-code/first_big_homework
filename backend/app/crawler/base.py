from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class CrawlRequest:
    platform: str
    keyword: str | None = None
    limit: int = 20
    extra: dict = field(default_factory=dict)


@dataclass(slots=True)
class CrawlResult:
    platform: str
    url: str
    title: str
    raw_content: str
    publish_time: str
    raw_json: dict = field(default_factory=dict)


class BaseCrawler(Protocol):
    platform: str

    def crawl(self, request: CrawlRequest) -> list[CrawlResult]:
        """Return public or authorized low-frequency documents for one platform."""


class CrawlerRegistry:
    def __init__(self):
        self._crawlers: dict[str, BaseCrawler] = {}

    def register(self, crawler: BaseCrawler) -> None:
        self._crawlers[crawler.platform] = crawler

    def get(self, platform: str) -> BaseCrawler:
        if platform not in self._crawlers:
            raise KeyError(f"crawler not registered: {platform}")
        return self._crawlers[platform]

    def platforms(self) -> list[str]:
        return sorted(self._crawlers)
