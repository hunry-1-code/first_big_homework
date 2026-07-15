from __future__ import annotations

import html
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.errors import CrawlerError
from app.crawler.rss import USER_AGENT, _matches_keyword, extract_article_text


SEARCH_URL = "http://search.people.cn/search-platform/front/search"


def _plain_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return " ".join(html.unescape(text).split())


def _publish_time(value: object) -> str | None:
    if value in (None, ""):
        return None
    try:
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class PeopleNewsCrawler:
    platform = "news_people"

    def __init__(
        self,
        client,
        rss_fallback=None,
        article_extractor: Callable[[str], str | None] | None = None,
        minimum_content_length: int = 50,
        freshness_days: int = 45,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.rss_fallback = rss_fallback
        self.article_extractor = article_extractor or extract_article_text
        self.minimum_content_length = max(1, int(minimum_content_length))
        self.freshness_days = max(1, int(freshness_days))
        self.now = now or (lambda: datetime.now(timezone.utc))

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        limit = min(5, request.limit)
        keyword = (request.keyword or "").strip()
        rows: list[RawDocument] = []
        if keyword:
            try:
                payload = self.client.post_json(
                    SEARCH_URL,
                    json={
                        "key": keyword,
                        "page": 1,
                        "limit": limit,
                        "hasTitle": True,
                        "hasContent": True,
                        "isFuzzy": True,
                        "type": 0,
                        "sortType": 2,
                        "startTime": 0,
                        "endTime": 0,
                    },
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json, text/plain, */*",
                        "Origin": "http://search.people.cn",
                        "Referer": "http://search.people.cn/",
                    },
                )
                if str(payload.get("code")) != "0":
                    raise CrawlerError(
                        self.platform,
                        f"CRAWL_API_{payload.get('code')}",
                        str(payload.get("message") or "People.cn search failed"),
                        False,
                    )
                records = (payload.get("data") or {}).get("records") or []
                for record in records[:limit]:
                    document = self._map_record(record)
                    if document is None:
                        continue
                    # 关键词二次过滤：API 模糊搜索过宽，标题必须匹配关键词
                    if keyword and not _matches_keyword(document.title, keyword):
                        continue
                    rows.append(document)
            except Exception:
                rows = []
        if rows:
            return rows[:limit]
        return self._fallback(request, limit)

    def _map_record(self, record: dict) -> RawDocument | None:
        url = str(record.get("url") or record.get("originUrl") or "").strip()
        title = _plain_text(record.get("title") or record.get("sourcetitle"))
        if not url or not title:
            return None
        fallback = _plain_text(
            record.get("contentOriginal") or record.get("content") or record.get("subtitle")
        )
        extracted = self.article_extractor(url)
        content = (extracted or fallback).strip()[:5000]
        if len(content) < self.minimum_content_length:
            return None
        source_id = record.get("id") or record.get("contentId") or url
        return RawDocument(
            platform=self.platform,
            source_url=url,
            source_article_id=str(source_id),
            title=title,
            raw_content=content,
            source_type="news",
            author=_plain_text(record.get("author") or record.get("originName")) or None,
            publish_time=_publish_time(record.get("inputTime") or record.get("displayTime")),
            content_type="text",
            raw_json={
                "origin_name": record.get("originName"),
                "domain": record.get("domain"),
                "search_source": "people_search",
            },
        )

    def _fallback(self, request: CrawlRequest, limit: int) -> list[RawDocument]:
        if self.rss_fallback is None:
            return []
        cutoff = self.now().astimezone(timezone.utc) - timedelta(days=self.freshness_days)
        fresh = []
        for document in self.rss_fallback.crawl(
            CrawlRequest(self.platform, request.keyword, limit, request.mode, request.extra)
        ):
            published = _parse_datetime(document.publish_time)
            if published is not None and published >= cutoff:
                document.platform = self.platform
                fresh.append(document)
            if len(fresh) >= limit:
                break
        return fresh
