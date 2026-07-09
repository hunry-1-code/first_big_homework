from __future__ import annotations

from app.crawler.base import CrawlRequest, CrawlResult


class SampleCrawler:
    platform = "sample"

    def crawl(self, request: CrawlRequest) -> list[CrawlResult]:
        keyword = request.keyword or "舆情"
        return [
            CrawlResult(
                platform=self.platform,
                url=f"sample://{keyword}/1",
                title=f"{keyword} 样例报道",
                raw_content=f"{keyword} 相关样例正文，供爬虫接口联调。",
                publish_time="2026-07-10T08:00:00+08:00",
                raw_json={"source": "sample", "keyword": keyword},
            )
        ]
