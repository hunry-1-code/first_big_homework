from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
import html
import re

import requests
import trafilatura

from app.crawler.base import CrawlRequest, RawDocument


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)
RSS_ACCEPT = "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"


def _keyword_terms(keyword: str) -> list[str]:
    parts = [keyword] if not any(ch.isspace() for ch in keyword) else keyword.split()
    aliases = {
        "人工智能": ("AI", "AIGC", "大模型"),
    }
    terms = list(parts)
    for part in parts:
        terms.extend(aliases.get(part, ()))
    return list(dict.fromkeys(terms))


def _matches_keyword(text: str, keyword: str) -> bool:
    folded = text.casefold()
    for term in _keyword_terms(keyword):
        folded_term = term.casefold()
        if folded_term.isascii() and folded_term.isalnum():
            if re.search(
                rf"(?<![a-z0-9]){re.escape(folded_term)}(?![a-z0-9])", folded
            ):
                return True
        elif folded_term in folded:
            return True
    return False


def _visible_text(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def _text(node, names: tuple[str, ...]) -> str | None:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag in names and child.text:
            return child.text.strip()
    return None


def extract_article_text(url: str) -> str | None:
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            },
            timeout=10,
        )
        response.raise_for_status()
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length > 5 * 1024 * 1024 or len(response.content) > 5 * 1024 * 1024:
            return None
        extracted = trafilatura.extract(
            response.content,
            include_title=False,
            include_author=False,
            include_date=False,
            output_format="txt",
        )
        return extracted.strip() if extracted else None
    except Exception:
        return None


class RssCrawler:
    platform = "rss"

    def __init__(
        self,
        client,
        feed_url: str,
        platform: str = "rss",
        article_extractor: Callable[[str], str | None] | None = None,
        minimum_content_length: int = 1,
    ):
        self.platform = platform
        self.client = client
        self.feed_url = feed_url
        self.article_extractor = article_extractor or extract_article_text
        self.minimum_content_length = max(1, int(minimum_content_length))

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        root = ET.fromstring(
            self.client.get_text(
                self.feed_url,
                prefer_xml=True,
                headers={"User-Agent": USER_AGENT, "Accept": RSS_ACCEPT},
            )
        )
        nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
        documents = []
        for node in nodes[: max(request.limit * 5, 20)]:
            title = _text(node, ("title",)) or ""
            content = _text(node, ("content", "description", "summary")) or ""
            item_id = _text(node, ("guid", "id", "contId"))
            link = _text(node, ("link",))
            if not link:
                for child in list(node):
                    if child.tag.rsplit("}", 1)[-1] == "link" and child.attrib.get("href"):
                        link = child.attrib["href"]
                        break
            if not link:
                continue
            full_text = self.article_extractor(link) or content
            full_text = full_text.strip()[:5000]
            if len(full_text) < self.minimum_content_length:
                continue

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
            if len(documents) >= request.limit:
                break
        return documents
