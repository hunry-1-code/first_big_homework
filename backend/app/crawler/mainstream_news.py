from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from app.crawler.base import CrawlRequest, RawDocument


SOURCE_ORDER = (
    "news_people",
    "news_36kr",
    "news_thepaper",
    "news_infoq",
    "news_sspai",
)


def _normalized_url(url: str) -> str:
    parsed = urlsplit((url or "").strip())
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, "")
    )


class MainstreamNewsCrawler:
    platform = "mainstream_news"

    def __init__(self, sources, comment_dispatcher=None) -> None:
        by_platform = {source.platform: source for source in sources}
        self.sources = [by_platform[name] for name in SOURCE_ORDER if name in by_platform]
        self.comment_dispatcher = comment_dispatcher
        self.last_source_counts = {name: 0 for name in SOURCE_ORDER}
        self.last_errors: list[dict[str, str]] = []

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        target = min(25, request.limit)
        base, remainder = divmod(target, len(SOURCE_ORDER))
        quotas = {
            name: min(5, base + (1 if index < remainder else 0))
            for index, name in enumerate(SOURCE_ORDER)
        }
        self.last_source_counts = {name: 0 for name in SOURCE_ORDER}
        self.last_errors = []
        documents: list[RawDocument] = []
        seen: set[str] = set()
        for source in self.sources:
            quota = quotas[source.platform]
            if quota <= 0:
                continue
            try:
                rows = source.crawl(
                    CrawlRequest(
                        platform=source.platform,
                        keyword=request.keyword,
                        limit=quota,
                        mode=request.mode,
                        extra=request.extra,
                    )
                )
            except Exception as exc:
                self.last_errors.append(
                    {"platform": source.platform, "message": str(exc)[:240]}
                )
                continue
            for document in rows[:quota]:
                key = _normalized_url(document.source_url)
                if not key or key in seen:
                    continue
                seen.add(key)
                document.platform = source.platform
                documents.append(document)
                self.last_source_counts[source.platform] += 1
                if len(documents) >= target:
                    return documents
        return documents

    def fetch_comments(self, document: RawDocument, limit: int = 10):
        if self.comment_dispatcher is None:
            from app.crawler.news_comments import NewsCommentResult

            return NewsCommentResult(status="unsupported")
        return self.comment_dispatcher.fetch(document, limit=min(10, limit))
