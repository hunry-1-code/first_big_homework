from __future__ import annotations

from urllib.parse import urlsplit

from app.preprocessing.normalizer import parse_metric, parse_publish_time


REQUIRED_JSON_FIELDS = ("platform", "url", "title", "raw_content", "publish_time")


def _invalid_required(item: dict, field: str) -> bool:
    value = item.get(field)
    if value is None:
        return True
    if field in {"platform", "url", "title", "raw_content", "publish_time"}:
        return not isinstance(value, str) or not value.strip()
    return False


def validate_json_documents(documents: list[dict]) -> tuple[list[dict], list[dict]]:
    normalized = []
    errors = []
    for index, item in enumerate(documents):
        if not isinstance(item, dict):
            errors.append({"index": index, "message": "每条数据必须是对象"})
            continue
        missing = [field for field in REQUIRED_JSON_FIELDS if _invalid_required(item, field)]
        if missing:
            errors.append({"index": index, "missing": missing, "message": f"缺少或无效字段: {', '.join(missing)}"})
            continue

        parsed_url = urlsplit(item["url"].strip())
        if parsed_url.scheme not in {"http", "https", "sample", "rss"}:
            errors.append({"index": index, "field": "url", "message": "url 协议不受支持"})
            continue
        publish_time, time_warnings = parse_publish_time(item["publish_time"])
        if publish_time is None or "NORMALIZE_TIME_PARSE_FAILED" in time_warnings:
            errors.append({"index": index, "field": "publish_time", "message": "发布时间格式无效"})
            continue

        normalized.append(
            {
                "platform": item["platform"].strip(),
                "url": item["url"].strip(),
                "source_article_id": item.get("source_article_id"),
                "source_type": item.get("source_type", "sample"),
                "title": item["title"].strip(),
                "raw_content": item["raw_content"],
                "content_type": item.get("content_type"),
                "clean_content": item.get("clean_content", ""),
                "raw_json": dict(item),
                "publish_time": item["publish_time"],
                "author": item.get("author"),
                "author_id": item.get("author_id"),
                "author_followers": parse_metric(item.get("author_followers")),
                "author_verified": item.get("author_verified"),
                "author_type": item.get("author_type"),
                "likes_count": parse_metric(item.get("likes_count", item.get("like_count"))),
                "comments_count": parse_metric(item.get("comments_count", item.get("comment_count"))),
                "reposts_count": parse_metric(item.get("reposts_count", item.get("repost_count"))),
                "views_count": parse_metric(item.get("views_count", item.get("view_count"))),
                "clean_status": item.get("clean_status", "pending"),
                "clean_error": item.get("clean_error", ""),
            }
        )
    return normalized, errors
