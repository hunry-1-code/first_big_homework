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
    """标题是否匹配搜索关键词。两层策略：精确子串 → jieba 分词松散匹配。"""
    if not keyword or not keyword.strip():
        return True
    folded = text.casefold()
    # 第1层：完整子串匹配
    for term in _keyword_terms(keyword):
        folded_term = term.casefold()
        if folded_term.isascii() and folded_term.isalnum():
            if re.search(
                rf"(?<![a-z0-9]){re.escape(folded_term)}(?![a-z0-9])", folded
            ):
                return True
        elif folded_term in folded:
            return True

    # 第2层：jieba 分词松散匹配（核心词必中 + 其余词 >= 50%）
    try:
        import jieba
        kw = keyword.strip()
        # 取最长 term
        kw_tokens = [t for t in jieba.lcut(kw) if len(t.strip()) >= 2]
        if len(kw_tokens) <= 1:
            return False
        # 标题归一化 + 分词
        text_norm = re.sub(r'[\s　「」【】《》\"\"\'\'、。，；：！？…—～～·]+', '', folded)
        title_tokens = set(jieba.lcut(text_norm))
        # 核心词（最长）必须在标题中
        core = max(kw_tokens, key=len)
        core_norm = re.sub(r'[\s　「」【】《》\"\"\'\'、。，；：！？…—～～·]+', '', core.casefold())
        core_ok = core_norm in text_norm or any(core_norm in t for t in title_tokens)
        if not core_ok:
            return False
        rest = [t for t in kw_tokens if t != core]
        if not rest:
            return True
        matched = 0
        for rt in rest:
            rt_norm = re.sub(r'[\s　「」【】《》\"\"\'\'、。，；：！？…—～～·]+', '', rt.casefold())
            if rt_norm in text_norm or any(rt_norm in t for t in title_tokens):
                matched += 1
        return matched / len(rest) >= 0.5
    except Exception:
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
            include_tables=False,
            include_images=False,
            include_formatting=False,
            include_links=False,
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
        keyword = (request.keyword or "").strip()
        nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
        documents = []
        for node in nodes[: max(request.limit * 5, 20)]:
            title = _text(node, ("title",)) or ""
            # 关键词过滤：有搜索词时标题必须匹配
            if keyword and not _matches_keyword(title, keyword):
                continue
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
