from __future__ import annotations

import html
import re
from typing import Callable

from app.crawler.errors import detect_blocked_content
from app.preprocessing.result import StageResult


EXTRACT_VERSION = "v1"
def _visible_text(raw_content: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_content or "", "html.parser")
        for node in soup(["script", "style", "noscript", "svg", "form"]):
            node.decompose()
        return "\n".join(
            line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
        )
    except ImportError:
        text = re.sub(r"<script[\s\S]*?</script>", " ", raw_content or "", flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "\n", text)
        return "\n".join(line.strip() for line in html.unescape(text).splitlines() if line.strip())


def _minimum_length(source_type: str) -> int:
    return {"social": 20, "hotlist": 5, "rss": 40, "sample": 5}.get(source_type, 100)


def _is_valid(text: str | None, source_type: str) -> bool:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text or detect_blocked_content(text):
        return False
    effective = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text)
    if len(effective) < _minimum_length(source_type):
        return False
    return len(effective) / max(1, len(text)) >= 0.35


def _trafilatura(raw_content: str) -> str | None:
    try:
        import trafilatura
    except ImportError:
        return None
    return trafilatura.extract(
        raw_content,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )


def _readability(raw_content: str) -> str | None:
    try:
        from readability import Document
    except ImportError:
        return None
    return _visible_text(Document(raw_content).summary())


def _bs4_article(raw_content: str, platform: str | None) -> str | None:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    soup = BeautifulSoup(raw_content, "html.parser")
    selectors = ["article", "main", ".article-content", ".content", "#content"]
    if platform == "weibo":
        selectors.insert(0, ".detail_wbtext_4CRf9")
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            return "\n".join(line.strip() for line in node.get_text("\n").splitlines() if line.strip())
    return None


def extract_content(
    raw_content: str,
    content_type: str = "html",
    source_type: str = "news",
    platform: str | None = None,
) -> StageResult:
    raw_content = raw_content or ""
    if content_type in {"text", "json"} and not re.search(r"<[^>]+>", raw_content):
        if _is_valid(raw_content, source_type):
            return StageResult.success(
                {"text": raw_content.strip(), "extraction_method": "plain_text", "extraction_degraded": False},
                EXTRACT_VERSION,
            )
        return StageResult.failed(["EXTRACT_ALL_METHODS_FAILED"], version=EXTRACT_VERSION)

    methods: list[tuple[str, Callable[[], str | None], bool]] = [
        ("trafilatura", lambda: _trafilatura(raw_content), False),
        ("readability", lambda: _readability(raw_content), False),
        ("bs4", lambda: _bs4_article(raw_content, platform), False),
        ("fallback", lambda: _visible_text(raw_content), True),
    ]
    warnings: list[str] = []
    for name, method, degraded in methods:
        try:
            text = method()
        except Exception:
            warnings.append("EXTRACT_PARSER_ERROR")
            continue
        if _is_valid(text, source_type):
            data = {
                "text": (text or "").strip(),
                "extraction_method": name,
                "extraction_degraded": degraded,
            }
            if degraded:
                return StageResult.degraded(
                    data,
                    [*warnings, "EXTRACT_FALLBACK_USED"],
                    EXTRACT_VERSION,
                )
            if warnings:
                return StageResult.degraded(data, warnings, EXTRACT_VERSION)
            return StageResult.success(data, EXTRACT_VERSION)
    return StageResult.failed(
        ["EXTRACT_ALL_METHODS_FAILED"],
        warnings=warnings,
        version=EXTRACT_VERSION,
    )


def extract_main_text(raw_content: str) -> str:
    result = extract_content(raw_content, "html", "sample")
    return result.data.get("text", "")
