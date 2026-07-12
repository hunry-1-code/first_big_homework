from __future__ import annotations

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.errors import raise_for_api_error


class QianfanSearchCrawler:
    platform = "baidu"

    def __init__(
        self,
        client,
        api_key: str,
        base_url: str = "https://qianfan.baidubce.com",
        search_path: str = "/v2/ai_search/web_search",
        maximum_top_k: int = 50,
    ):
        self.client = client
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.search_path = "/" + search_path.lstrip("/")
        self.maximum_top_k = min(50, max(1, int(maximum_top_k)))

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        payload = self.client.post_json(
            f"{self.base_url}{self.search_path}",
            headers=self._headers(),
            json={
                "messages": [{"role": "user", "content": request.keyword or ""}],
                "search_source": "baidu_search_v2",
                "resource_type_filter": [
                    {"type": "web", "top_k": min(self.maximum_top_k, request.limit)}
                ],
                "safe_search": True,
            },
        )
        raise_for_api_error(payload, self.platform)
        documents = []
        for item in payload.get("references", [])[: request.limit]:
            url = item.get("url")
            if not url:
                continue
            documents.append(
                RawDocument(
                    platform=self.platform,
                    source_url=url,
                    source_article_id=str(item.get("id") or url),
                    title=item.get("title") or item.get("web_anchor") or request.keyword or "",
                    raw_content=item.get("content") or item.get("snippet") or "",
                    source_type="news",
                    author=item.get("website") or item.get("web_anchor"),
                    publish_time=item.get("date"),
                    content_type="text",
                    raw_json=item,
                )
            )
        return documents

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }


class QianfanTrendingCrawler(QianfanSearchCrawler):
    platform = "baidu_hot"

    def __init__(
        self,
        client,
        api_key: str,
        base_url: str = "https://qianfan.baidubce.com",
        trending_path: str = "/v2/tools/baidu_trending",
    ):
        super().__init__(client, api_key, base_url)
        self.trending_path = "/" + trending_path.lstrip("/")

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        payload = self.client.get_json(
            f"{self.base_url}{self.trending_path}",
            headers=self._headers(),
            params={"tab": request.extra.get("tab", "livelihood")},
        )
        raise_for_api_error(payload, self.platform)
        documents = []
        for item in payload.get("data", [])[: request.limit]:
            title = item.get("word") or item.get("query") or ""
            url = item.get("url") or f"https://www.baidu.com/s?wd={title}"
            documents.append(
                RawDocument(
                    platform=self.platform,
                    source_url=url,
                    source_article_id=str(item.get("query") or title),
                    title=title,
                    raw_content=item.get("desc") or title,
                    source_type="hotlist",
                    content_type="text",
                    raw_json=item,
                )
            )
        return documents
