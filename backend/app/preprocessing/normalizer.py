from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from app.preprocessing.result import StageResult


NORMALIZE_VERSION = "v1"
TRACKING_PARAMETERS = {
    "from",
    "source",
    "spm",
    "ref",
    "refer",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
PLATFORM_ALIASES = {
    "b站": "bilibili",
    "哔哩哔哩": "bilibili",
    "bilibili": "bilibili",
    "微博": "weibo",
    "weibo": "weibo",
    "微博热搜": "weibo_hot",
    "weibo_hot": "weibo_hot",
    "知乎": "zhihu",
    "zhihu": "zhihu",
    "知乎热榜": "zhihu_hot",
    "zhihu_hot": "zhihu_hot",
    "小红书": "xiaohongshu",
    "xiaohongshu": "xiaohongshu",
    "抖音": "douyin",
    "douyin": "douyin",
    "百度": "baidu",
    "baidu": "baidu",
    "百度热搜": "baidu_hot",
    "baidu_hot": "baidu_hot",
    "rss": "rss",
    "sample": "sample",
}


def _plain(value: Any) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value))
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_url(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme.lower() in {"sample", "rss"}:
        return value.split("#", 1)[0]
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    host = parts.hostname.lower()
    port = parts.port
    netloc = host
    if port and not ((parts.scheme.lower() == "http" and port == 80) or (parts.scheme.lower() == "https" and port == 443)):
        netloc = f"{host}:{port}"
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMETERS and not key.lower().startswith("utm_")
    ]
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", urlencode(query), ""))


def parse_metric(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip().lower().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group())
    multiplier = 1
    if "亿" in text:
        multiplier = 100_000_000
    elif "万" in text or text.endswith("w"):
        multiplier = 10_000
    elif text.endswith("k"):
        multiplier = 1_000
    elif text.endswith("m"):
        multiplier = 1_000_000
    return max(0, int(number * multiplier))


def parse_publish_time(value: Any) -> tuple[datetime | None, list[str]]:
    if value in (None, ""):
        return None, []
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, timezone.utc)
    else:
        text = str(value).strip()
        try:
            from dateutil import parser

            parsed = parser.parse(text)
        except (ImportError, ValueError, TypeError, OverflowError):
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None, ["NORMALIZE_TIME_PARSE_FAILED"]
    warnings: list[str] = []
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        warnings.append("timezone_assumed")
    return parsed.astimezone(timezone.utc), warnings


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _first_present(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def normalize_document(document: Any) -> StageResult:
    if is_dataclass(document):
        source = asdict(document)
    elif isinstance(document, dict):
        source = dict(document)
    else:
        return StageResult.failed(["NORMALIZE_MISSING_REQUIRED_FIELD"], version=NORMALIZE_VERSION)

    platform_input = _plain(source.get("platform"))
    platform = PLATFORM_ALIASES.get((platform_input or "").lower(), (platform_input or "").lower())
    url = normalize_url(source.get("source_url") or source.get("url"))
    source_id = _plain(source.get("source_article_id"))
    raw_content = source.get("raw_content")
    if raw_content is None:
        raw_content = source.get("content")
    raw_content = "" if raw_content is None else str(raw_content)
    title = _plain(source.get("title")) or ""

    if not platform or (not url and not source_id) or (not raw_content and not title):
        return StageResult.failed(
            ["NORMALIZE_MISSING_REQUIRED_FIELD"],
            data={"original": source},
            version=NORMALIZE_VERSION,
        )

    warnings: list[str] = []
    publish_time, time_warnings = parse_publish_time(source.get("publish_time"))
    warnings.extend(time_warnings)
    if source.get("publish_time") and publish_time is None:
        warnings.append("NORMALIZE_TIME_PARSE_FAILED")

    if not url:
        warnings.append("NORMALIZE_INVALID_URL")
    content_type = source.get("content_type")
    if content_type not in {"html", "text", "json"}:
        content_type = "html" if re.search(r"<[^>]+>", raw_content) else "text"

    normalized = {
        **source,
        "platform": platform,
        "source_type": source.get("source_type") or "news",
        "source_article_id": source_id,
        "url": url,
        "source_url": url,
        "url_hash": hashlib.sha256((url or f"{platform}:{source_id}").encode("utf-8")).hexdigest(),
        "title": title,
        "raw_content": raw_content,
        "content_type": content_type,
        "publish_time": publish_time,
        "author": _plain(source.get("author")),
        "author_id": _plain(source.get("author_id")),
        "author_type": source.get("author_type") or "unknown",
        "author_verified": source.get("author_verified"),
        "author_followers": parse_metric(source.get("author_followers")),
        "likes_count": parse_metric(_first_present(source, "likes_count", "like_count")),
        "comments_count": parse_metric(_first_present(source, "comments_count", "comment_count")),
        "reposts_count": parse_metric(_first_present(source, "reposts_count", "repost_count")),
        "views_count": parse_metric(_first_present(source, "views_count", "view_count")),
        "language": source.get("language") or "unknown",
        "raw_json": _json_safe(source.get("raw_json") or source.get("raw_data") or source),
        "normalize_version": NORMALIZE_VERSION,
    }
    if warnings:
        return StageResult.degraded(normalized, list(dict.fromkeys(warnings)), NORMALIZE_VERSION)
    return StageResult.success(normalized, NORMALIZE_VERSION)
