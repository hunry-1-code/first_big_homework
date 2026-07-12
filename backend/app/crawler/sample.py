from __future__ import annotations

from app.crawler.base import CrawlRequest, RawDocument


class SampleCrawler:
    platform = "sample"

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        keyword = request.keyword or "舆情"
        return [
            RawDocument(
                platform=self.platform,
                source_url=f"sample://{keyword}/1",
                source_article_id=f"{keyword}-1",
                title=f"{keyword} 样例报道",
                raw_content=(f"{keyword} 相关样例正文，用于爬虫、清洗和任务接口联调。" * 8),
                source_type="sample",
                content_type="text",
                publish_time="2026-07-10T08:00:00+08:00",
                author="系统样例",
                raw_json={"source": "sample", "keyword": keyword},
            )
        ][: request.limit]
