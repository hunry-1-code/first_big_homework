from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class CrawlRequest:
    platform: str
    keyword: str | None = None
    limit: int = 20
    mode: str = "search"
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.limit = max(1, int(self.limit))


@dataclass(slots=True)
class RawDocument:
    platform: str
    source_url: str
    title: str
    raw_content: str
    source_type: str = "news"
    source_article_id: str | None = None
    content_type: str = "text"
    author: str | None = None
    author_id: str | None = None
    author_followers: int | None = None
    author_verified: bool | None = None
    author_type: str | None = None
    publish_time: str | None = None
    likes_count: int | None = None
    comments_count: int | None = None
    reposts_count: int | None = None
    views_count: int | None = None
    language: str = "unknown"
    raw_json: dict[str, Any] = field(default_factory=dict)
    clean_status: str = "pending"
    http_status: int | None = None
    fetch_status: str = "success"
    fetch_error: str | None = None

    @property
    def url(self) -> str:
        return self.source_url


@dataclass(slots=True)
class CrawlIssue:
    platform: str
    code: str
    message: str
    retryable: bool = False


@dataclass(slots=True)
class CrawlBatch:
    keyword: str | None
    target_count: int
    documents: list[RawDocument] = field(default_factory=list)
    errors: list[CrawlIssue] = field(default_factory=list)
    platform_counts: dict[str, int] = field(default_factory=dict)


class BaseCrawler(Protocol):
    platform: str

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        """Return public or authorized low-frequency documents for one platform."""


class CrawlerRegistry:
    def __init__(self) -> None:
        self._crawlers: dict[str, BaseCrawler] = {}

    def register(self, crawler: BaseCrawler) -> None:
        self._crawlers[crawler.platform] = crawler

    def get(self, platform: str) -> BaseCrawler:
        if platform not in self._crawlers:
            raise KeyError(f"crawler not registered: {platform}")
        return self._crawlers[platform]

    def platforms(self) -> list[str]:
        return sorted(self._crawlers)
