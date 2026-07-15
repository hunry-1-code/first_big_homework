from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.comments import RawComment
from app.crawler.errors import CrawlerError, raise_for_api_error


def _plain(value: str | None) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(value or "")).strip()


class BilibiliCrawler:
    platform = "bilibili"

    def __init__(self, client, base_url: str = "https://api.bilibili.com"):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self._device_initialized = False
        self._device_cookie = ""

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://search.bilibili.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def _initialize_public_device(self) -> None:
        if self._device_initialized:
            return
        try:
            payload = self.client.get_json(
                f"{self.base_url}/x/frontend/finger/spi",
                headers=self._headers(),
            )
            raise_for_api_error(payload, self.platform)
        except CrawlerError:
            return
        data = payload.get("data") or {}
        buvid3 = data.get("b_3")
        buvid4 = data.get("b_4")
        cookies = []
        session = getattr(self.client, "session", None)
        cookie_jar = getattr(session, "cookies", None)
        for name, value in (("buvid3", buvid3), ("buvid4", buvid4)):
            if not value:
                continue
            cookies.append(f"{name}={value}")
            if cookie_jar is not None:
                cookie_jar.set(name, value, domain=".bilibili.com")
        self._device_cookie = "; ".join(cookies)
        self._device_initialized = True

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        self._initialize_public_device()
        headers = self._headers()
        if self._device_cookie:
            headers["Cookie"] = self._device_cookie

        limit = max(1, request.limit)
        # 双搜：专栏（正文长）+ 视频（评论多），各取一半配额，合并去重
        documents: list[RawDocument] = []
        seen_ids: set[str] = set()

        for search_type in ("article", "video"):
            type_limit = max(1, (limit - len(documents)) // (2 if search_type == "article" else 1))
            if type_limit <= 0:
                break
            try:
                payload = self.client.get_json(
                    f"{self.base_url}/x/web-interface/search/type",
                    headers=headers,
                    params={
                        "search_type": search_type,
                        "keyword": request.keyword or "",
                        "page": request.extra.get("page", 1),
                        "page_size": min(50, type_limit * 2),
                    },
                )
                raise_for_api_error(payload, self.platform)
                items = (payload.get("data") or {}).get("result") or []
            except Exception:
                continue

            for item in items:
                if len(documents) >= limit:
                    break
                bvid = str(item.get("bvid") or "")
                art_id = bvid or str(item.get("id") or item.get("cvid") or item.get("bid") or "")
                if not art_id or art_id in seen_ids:
                    continue
                seen_ids.add(art_id)
                publish_time = item.get("pubdate") or item.get("ctime")
                if isinstance(publish_time, (int, float)):
                    publish_time = datetime.fromtimestamp(publish_time, timezone.utc).isoformat()

                full_content = _plain(item.get("description") or "")
                author_name = item.get("author") or ""
                author_mid = str(item.get("mid")) if item.get("mid") is not None else ""
                view_count = item.get("play")
                like_count = item.get("favorites")
                reply_count = item.get("review")

                try:
                    if bvid:
                        detail = self.client.get_json(
                            f"{self.base_url}/x/web-interface/view",
                            headers=headers,
                            params={"bvid": bvid},
                        )
                        if detail.get("code") == 0:
                            d = detail.get("data") or {}
                            full_content = d.get("desc") or full_content
                            owner = d.get("owner") or {}
                            author_name = owner.get("name") or author_name
                            author_mid = str(owner.get("mid")) if owner.get("mid") else author_mid
                            stats = d.get("stat") or {}
                            view_count = stats.get("view") or view_count
                            like_count = stats.get("like") or like_count
                            reply_count = stats.get("reply") or reply_count
                    else:
                        detail = self.client.get_json(
                            f"{self.base_url}/x/article/view",
                            headers=headers,
                            params={"id": int(art_id)},
                        )
                        if detail.get("code") == 0:
                            d = detail.get("data") or {}
                            full_content = d.get("content") or full_content
                            author_name = d.get("author_name") or author_name
                            author_mid = str(d.get("mid")) if d.get("mid") else author_mid
                            stats = d.get("stats") or {}
                            view_count = stats.get("view") or view_count
                            like_count = stats.get("like") or like_count
                            reply_count = stats.get("reply") or reply_count
                except Exception:
                    pass

                documents.append(
                    RawDocument(
                        platform=self.platform,
                        source_url=(f"https://www.bilibili.com/video/{art_id}" if bvid else f"https://www.bilibili.com/read/cv{art_id}"),
                        source_article_id=art_id,
                        title=_plain(item.get("title")),
                        raw_content=full_content,
                        source_type="social",
                        author=author_name,
                        author_id=author_mid,
                        publish_time=publish_time,
                        likes_count=like_count,
                        comments_count=reply_count,
                        views_count=view_count,
                        content_type="video" if bvid else "text",
                        raw_json=item,
                    )
                )
        return documents

    @staticmethod
    def _article_id_pattern(art_id: str) -> bool:
        """判断 ID 是否是专栏文章格式（纯数字ID）。"""
        return art_id.isdigit() and len(art_id) >= 6

    def fetch_comments(self, oid: str, *, page: int = 1, limit: int = 50) -> list[RawComment]:
        """Fetch public first-level comments and their replies without TikHub."""
        self._initialize_public_device()
        # B站 API ps 上限因视频而异，安全值 20
        ps = min(limit, 20)
        if str(oid).upper().startswith("BV"):
            try:
                detail = self.client.get_json(
                    f"{self.base_url}/x/web-interface/view",
                    headers=self._headers(), params={"bvid": oid},
                )
                raise_for_api_error(detail, self.platform)
                oid = str((detail.get("data") or {}).get("aid") or "")
            except Exception:
                pass  # bvid→aid 失败则用 bvid 继续
            if not oid:
                return []
        try:
            oid_int = int(oid) if oid else 0
        except (ValueError, TypeError):
            return []
        if not oid_int:
            return []
        payload = self.client.get_json(
            f"{self.base_url}/x/v2/reply", headers=self._headers(),
            params={"type": 1, "oid": oid_int, "pn": page, "ps": ps, "sort": 2},
        )
        raise_for_api_error(payload, self.platform)
        replies = ((payload.get("data") or {}).get("replies") or [])
        result = []
        for item in replies[:limit]:
            if len(result) >= limit:
                break
            member = item.get("member") or {}
            result.append(RawComment(platform=self.platform, source_comment_id=str(item.get("rpid")), content=_plain(item.get("content", {}).get("message")), author=member.get("uname"), likes_count=int(item.get("like", 0) or 0), replies_count=int(item.get("rcount", 0) or 0), raw_json=item))
            for child in (item.get("replies") or [])[:20]:
                if len(result) >= limit:
                    break
                cm = child.get("member") or {}
                result.append(RawComment(platform=self.platform, source_comment_id=str(child.get("rpid")), parent_source_comment_id=str(item.get("rpid")), content=_plain(child.get("content", {}).get("message")), author=cm.get("uname"), likes_count=int(child.get("like", 0) or 0), raw_json=child))
        return result
