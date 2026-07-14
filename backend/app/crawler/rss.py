from __future__ import annotations

import xml.etree.ElementTree as ET

from app.crawler.base import CrawlRequest, RawDocument


def _text(node, names: tuple[str, ...]) -> str | None:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag in names and child.text:
            return child.text.strip()
    return None


class RssCrawler:
    platform = "rss"

    def __init__(self, client, feed_url: str, platform: str = "rss"):
        self.platform = platform
        self.client = client
        self.feed_url = feed_url

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        root = ET.fromstring(self.client.get_text(self.feed_url))
        nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
        documents = []
        for node in nodes[: request.limit * 3]:  # 多取一些，过滤后还有足够的
            title = _text(node, ("title",)) or ""
            # RSS 不支持关键词搜索，后过滤：标题不含关键词则跳过
            keyword = (request.keyword or "").strip()
            if keyword:
                kw_parts = [keyword] if not any(ch.isspace() for ch in keyword) else keyword.split()
                if not any(p in title for p in kw_parts):
                    continue
            content = _text(node, ("content", "description", "summary")) or ""
            item_id = _text(node, ("guid", "id"))
            link = _text(node, ("link",))
            if not link:
                for child in list(node):
                    if child.tag.rsplit("}", 1)[-1] == "link" and child.attrib.get("href"):
                        link = child.attrib["href"]
                        break
            if not link:
                continue
            # 尝试从原文链接提取全文
            full_text = ""
            try:
                import trafilatura
                downloaded = trafilatura.fetch_url(link, timeout=10)
                if downloaded:
                    extracted = trafilatura.extract(downloaded, include_title=False,
                        include_author=False, include_date=False, output_format="text")
                    if extracted and len(extracted) > 200:
                        full_text = extracted[:5000]
            except Exception:
                pass  # trafilatura 失败时用 RSS description 兜底
            if not full_text:
                full_text = content  # RSS description 作为 fallback

            documents.append(
                RawDocument(
                    platform=self.platform,
                    source_url=link,
                    source_article_id=item_id or link,
                    title=title,
                    raw_content=full_text,
                    source_type="rss",
                    publish_time=_text(node, ("pubDate", "published", "updated")),
                    content_type="html" if "<" in full_text else "text",
                    raw_json={"feed_url": self.feed_url, "id": item_id},
                )
            )
        return documents
