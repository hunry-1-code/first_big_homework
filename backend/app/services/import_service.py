from __future__ import annotations


REQUIRED_JSON_FIELDS = ("platform", "url", "title", "raw_content", "publish_time")


def validate_json_documents(documents: list[dict]) -> tuple[list[dict], list[dict]]:
    normalized = []
    errors = []
    for index, item in enumerate(documents):
        if not isinstance(item, dict):
            errors.append({"index": index, "message": "每条数据必须是对象"})
            continue
        missing = [field for field in REQUIRED_JSON_FIELDS if field not in item]
        if missing:
            errors.append({"index": index, "missing": missing, "message": f"缺少字段: {', '.join(missing)}"})
            continue
        normalized.append(
            {
                "platform": item["platform"],
                "url": item["url"],
                "title": item["title"],
                "raw_content": item["raw_content"],
                "clean_content": item.get("clean_content", ""),
                "raw_json": dict(item),
                "publish_time": item["publish_time"],
                "clean_status": item.get("clean_status", "pending"),
                "clean_error": item.get("clean_error", ""),
            }
        )
    return normalized, errors
