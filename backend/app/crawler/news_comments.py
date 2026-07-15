from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.crawler.base import RawDocument
from app.crawler.comments import RawComment
from app.crawler.rss import USER_AGENT


@dataclass(slots=True)
class NewsCommentResult:
    status: str
    comments: list[RawComment] = field(default_factory=list)
    error: str | None = None


def _identifier(document: RawDocument) -> str | None:
    if document.source_article_id and str(document.source_article_id).isdigit():
        return str(document.source_article_id)
    patterns = {
        "news_sspai": r"/post/(\d+)",
        "news_thepaper": r"newsDetail_forward_(\d+)",
    }
    match = re.search(patterns.get(document.platform, r"$^"), document.source_url)
    return match.group(1) if match else None


class NewsCommentDispatcher:
    def __init__(self, sspai_client=None, thepaper_client=None) -> None:
        self.sspai_client = sspai_client
        self.thepaper_client = thepaper_client

    def fetch(self, document: RawDocument, limit: int = 10) -> NewsCommentResult:
        limit = min(10, max(1, int(limit)))
        if document.platform == "news_sspai" and self.sspai_client is not None:
            return self._fetch_sspai(document, limit)
        if document.platform == "news_thepaper" and self.thepaper_client is not None:
            return self._fetch_thepaper(document, limit)
        return NewsCommentResult(status="unsupported")

    def _fetch_sspai(self, document: RawDocument, limit: int) -> NewsCommentResult:
        article_id = _identifier(document)
        if article_id is None:
            return NewsCommentResult(status="failed", error="missing SSPAI article id")
        try:
            payload = self.sspai_client.get_json(
                "https://sspai.com/api/v2/comment/search/page/get",
                params={"article_id": article_id, "limit": limit, "offset": 0},
                headers={"User-Agent": USER_AGENT, "Referer": document.source_url},
            )
            if int(payload.get("error", 0)) != 0:
                raise ValueError(str(payload.get("msg") or "SSPAI comment API failed"))
            comments = []
            for item in (payload.get("data") or [])[:limit]:
                source_id = item.get("id")
                content = " ".join(str(item.get("comment") or "").split())
                if source_id in (None, "") or not content:
                    continue
                replies = item.get("reply") or []
                comments.append(
                    RawComment(
                        platform="news_sspai",
                        source_comment_id=str(source_id),
                        content=content,
                        author=((item.get("user") or {}).get("nickname") or None),
                        likes_count=int(item.get("likes_count") or 0),
                        replies_count=len(replies),
                        raw_json={"created_at": item.get("created_at"), "chosen": item.get("chosen")},
                    )
                )
            return NewsCommentResult(status="success" if comments else "empty", comments=comments)
        except Exception as exc:
            return NewsCommentResult(status="failed", error=str(exc)[:240])

    def _fetch_thepaper(self, document: RawDocument, limit: int) -> NewsCommentResult:
        article_id = _identifier(document)
        if article_id is None:
            return NewsCommentResult(status="failed", error="missing The Paper article id")
        try:
            payload = self.thepaper_client.get_json(
                f"https://cache.thepaper.cn/commentapi/news/comment/webOneList/{article_id}",
                headers={"User-Agent": USER_AGENT, "Referer": document.source_url},
            )
            if int(payload.get("code", 200)) != 200:
                raise ValueError(str(payload.get("msg") or "The Paper comment API failed"))
            comments = []
            for item in ((payload.get("data") or {}).get("list") or [])[:limit]:
                source_id = item.get("commentId")
                content = " ".join(str(item.get("content") or "").split())
                if source_id in (None, "") or not content:
                    continue
                user = item.get("userInfo") or {}
                replies = item.get("commentReply") or []
                comments.append(
                    RawComment(
                        platform="news_thepaper",
                        source_comment_id=str(source_id),
                        content=content,
                        author=item.get("userName") or user.get("sname") or None,
                        likes_count=int(item.get("originPraiseTimes") or item.get("praiseTimes") or 0),
                        replies_count=len(replies),
                        raw_json={"origin_create_time": item.get("originCreateTime"), "location": item.get("location")},
                    )
                )
            return NewsCommentResult(status="success" if comments else "empty", comments=comments)
        except Exception as exc:
            return NewsCommentResult(status="failed", error=str(exc)[:240])
