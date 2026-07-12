from __future__ import annotations

from urllib.parse import quote

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.errors import raise_for_api_error


class WeiboHotCrawler:
    platform = "weibo_hot"

    def __init__(self, client, base_url: str = "https://weibo.com"):
        self.client = client
        self.base_url = base_url.rstrip("/")

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        payload = self.client.get_json(
            f"{self.base_url}/ajax/side/hotSearch",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://weibo.com/"},
        )
        raise_for_api_error(payload, self.platform)
        items = (payload.get("data") or {}).get("realtime") or []
        documents = []
        for item in items[: request.limit]:
            title = item.get("note") or item.get("word") or ""
            documents.append(
                RawDocument(
                    platform=self.platform,
                    source_url=f"https://s.weibo.com/weibo?q={quote(title)}",
                    source_article_id=str(item.get("word_scheme") or title),
                    title=title,
                    raw_content=item.get("onboard_time_text") or title,
                    source_type="hotlist",
                    content_type="text",
                    raw_json=item,
                )
            )
        return documents
