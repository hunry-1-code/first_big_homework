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

    def __init__(self, client, feed_url: str):
        self.client = client
        self.feed_url = feed_url

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        root = ET.fromstring(self.client.get_text(self.feed_url))
        nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
        documents = []
        for node in nodes[: request.limit]:
            title = _text(node, ("title",)) or ""
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
            documents.append(
                RawDocument(
                    platform=self.platform,
                    source_url=link,
                    source_article_id=item_id or link,
                    title=title,
                    raw_content=content,
                    source_type="rss",
                    publish_time=_text(node, ("pubDate", "published", "updated")),
                    content_type="html" if "<" in content else "text",
                    raw_json={"feed_url": self.feed_url, "id": item_id},
                )
            )
        return documents
