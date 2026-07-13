import re
from collections.abc import Iterable


PARENT_KEYS = (
    "parent_id",
    "root_id",
    "reposted_from",
    "retweeted_status",
    "quoted_status",
)


def _article_text(article) -> str:
    return " ".join(
        str(value or "")
        for value in (
            getattr(article, "title", ""),
            getattr(article, "clean_content", ""),
            getattr(article, "raw_content", ""),
        )
    )


def _text_tokens(text: str) -> set[str]:
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text or ""))
    bigrams = {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}
    return bigrams | set(re.findall(r"[A-Za-z0-9_]{2,}", (text or "").lower()))


def explicit_parent_ids(article) -> list[str]:
    raw = getattr(article, "raw_json", {}) or {}
    values = []
    for key in PARENT_KEYS:
        value = raw.get(key)
        if isinstance(value, dict):
            value = value.get("id") or value.get("mid") or value.get("source_article_id")
        if value is not None:
            values.append(str(value))
    return values


def explicit_parent_authors(article) -> list[str]:
    text = _article_text(article)
    patterns = (
        r"//\s*@\s*([^\s:：/]{2,30})",
        r"(?:转自|转载自|来源)\s*[:：]?\s*@?([^\s，。；;:：/]{2,30})",
    )
    output = []
    for pattern in patterns:
        output.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return list(dict.fromkeys(value.strip() for value in output if value.strip()))


def normalize_author(value) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_-]+", "", str(value or "")).casefold()


def author_matches(first, second) -> bool:
    left = normalize_author(first)
    right = normalize_author(second)
    return len(left) >= 2 and len(right) >= 2 and (left in right or right in left)


def source_evidence(article) -> list[str]:
    return explicit_parent_authors(article)


def tokens(article) -> set[str]:
    title = getattr(article, "title", "") or ""
    content = getattr(article, "clean_content", "") or ""
    return _text_tokens(f"{title} {content[:300]}")


def keyword_or_entity_terms(article) -> set[str]:
    output = set()
    keywords = getattr(article, "keywords", None) or []
    if isinstance(keywords, dict):
        keywords = keywords.get("keywords", [])
    for item in keywords if isinstance(keywords, Iterable) and not isinstance(keywords, str) else []:
        value = item.get("term") if isinstance(item, dict) else item
        if str(value or "").strip():
            output.add(str(value).strip().casefold())

    entities = getattr(article, "entities", None) or {}
    if isinstance(entities, dict):
        for values in entities.values():
            if isinstance(values, str):
                values = [values]
            for value in values or []:
                if str(value or "").strip():
                    output.add(str(value).strip().casefold())

    if not output:
        output.update(_text_tokens(getattr(article, "title", "") or ""))
    return output


__all__ = [
    "author_matches",
    "explicit_parent_authors",
    "explicit_parent_ids",
    "keyword_or_entity_terms",
    "normalize_author",
    "source_evidence",
    "tokens",
]
