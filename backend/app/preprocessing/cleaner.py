from __future__ import annotations

import html
import re
import unicodedata

from app.preprocessing.result import StageResult


CLEAN_VERSION = "v1"
NOISE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^打开\s*APP\s*阅读全文$",
        r"^上一篇(?:[:：].*)?$",
        r"^下一篇(?:[:：].*)?$",
        r"^相关阅读(?:[:：].*)?$",
        r"^责任编辑(?:[:：].*)?$",
        r"^版权声明(?:[:：].*)?$",
        r"^返回首页$",
    )
]
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
MENTION_RE = re.compile(r"@[A-Za-z0-9_\-\u4e00-\u9fff]+")
TOPIC_RE = re.compile(r"#[^#\n]{1,50}#")
EMOTION_RE = re.compile(r"\[[^\]\n]{1,12}\]|[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _strip_html(text: str) -> str:
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    text = re.sub(r"<(script|style|noscript)[^>]*>[\s\S]*?</\1>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|article|section|li|h[1-6]|br)>", "\n", text, flags=re.IGNORECASE)
    return re.sub(r"<[^>]+>", " ", text)


def clean_document(text: str, platform: str | None = None) -> StageResult:
    original = text or ""
    normalized = html.unescape(_strip_html(original))
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", normalized)
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)

    mentions = list(dict.fromkeys(MENTION_RE.findall(normalized)))
    topics = list(dict.fromkeys(TOPIC_RE.findall(normalized)))
    urls = list(dict.fromkeys(URL_RE.findall(normalized)))
    emotions = list(dict.fromkeys(EMOTION_RE.findall(normalized)))

    removed_lines: list[str] = []
    paragraphs: list[str] = []
    for raw_line in normalized.split("\n"):
        line = re.sub(r"[ \t\u3000]+", " ", raw_line).strip()
        if not line:
            continue
        if any(pattern.match(line) for pattern in NOISE_PATTERNS):
            removed_lines.append(line)
            continue
        paragraphs.append(line)

    clean_content = "\n".join(paragraphs).strip()
    data = {
        "clean_content": clean_content,
        "mentions": mentions,
        "topics": topics,
        "urls": urls,
        "emotions": emotions,
        "removed_lines": removed_lines,
        "warnings": [],
        "statistics": {
            "original_length": len(original),
            "clean_length": len(clean_content),
            "removed_length": max(0, len(original) - len(clean_content)),
        },
        "clean_version": CLEAN_VERSION,
    }
    if not clean_content:
        return StageResult.failed(["CLEAN_EMPTY_AFTER_CLEANING"], data=data, version=CLEAN_VERSION)
    return StageResult.success(data, CLEAN_VERSION)


def clean_text(text: str) -> str:
    return clean_document(text).data.get("clean_content", "")
