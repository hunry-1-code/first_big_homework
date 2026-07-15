from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from app.propagation.evidence import keyword_or_entity_terms


def _article_terms(article, maximum: int) -> list[str]:
    terms = sorted(
        {
            str(term).strip()
            for term in keyword_or_entity_terms(article)
            if 2 <= len(str(term).strip()) <= 30
        }
    )
    return terms[:maximum]


def build_keyword_relations(
    articles,
    *,
    maximum_terms_per_article: int = 8,
    limit: int = 20,
) -> list[dict]:
    relations: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"article_ids": [], "platforms": set(), "example_titles": []}
    )
    for article in articles:
        terms = _article_terms(article, max(2, int(maximum_terms_per_article)))
        for first, second in combinations(terms, 2):
            key = tuple(sorted((first, second)))
            row = relations[key]
            article_id = int(article.id)
            if article_id not in row["article_ids"]:
                row["article_ids"].append(article_id)
            platform = str(getattr(article, "platform", "") or "").strip()
            if platform:
                row["platforms"].add(platform)
            title = str(getattr(article, "title", "") or "").strip()
            if title and title not in row["example_titles"] and len(row["example_titles"]) < 3:
                row["example_titles"].append(title[:120])

    output = []
    for terms, row in relations.items():
        article_ids = sorted(row["article_ids"])
        output.append(
            {
                "terms": list(terms),
                "article_ids": article_ids,
                "article_count": len(article_ids),
                "platform_count": len(row["platforms"]),
                "platforms": sorted(row["platforms"]),
                "example_titles": row["example_titles"],
            }
        )
    output.sort(
        key=lambda item: (
            -item["article_count"],
            -item["platform_count"],
            item["terms"],
        )
    )
    return output[: max(1, int(limit))]


__all__ = ["build_keyword_relations"]
