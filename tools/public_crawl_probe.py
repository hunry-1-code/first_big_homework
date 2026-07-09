"""Probe public Chinese web sources without bypassing anti-crawling controls.

The script sends one ordinary HTTP GET request per configured public URL,
extracts rough visible text from HTML/XML, and classifies whether the page is
usable for a course-project crawler. It does not solve captchas, reverse API
signatures, use proxy pools, or bypass access controls.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_KEYWORD = "舆情"
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_DELAY_SECONDS = 2.0


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 "
    "OpinionAnalysisCourseProbe/1.0"
)


BLOCK_HINTS = (
    "验证码",
    "安全验证",
    "访问异常",
    "请先登录",
    "sina visitor system",
    "forbidden",
    "captcha",
    "verify",
    "robot",
    "风控",
)

NO_RESULT_PATTERNS = (
    r"找到约\s*0\s*个结果",
    r"找到\s*0\s*个结果",
    r"暂无相关结果",
    r"没有找到相关",
)


@dataclass(frozen=True)
class SourceTarget:
    name: str
    category: str
    url_template: str
    notes: str

    def url(self, keyword: str) -> str:
        return self.url_template.format(keyword=quote(keyword))


@dataclass
class ProbeResult:
    name: str
    category: str
    url: str
    status_code: int | None
    ok: bool
    classification: str
    content_type: str
    bytes_received: int
    text_chars: int
    sample: str
    error: str
    notes: str


class VisibleTextParser(HTMLParser):
    """Small dependency-free visible text extractor for probe classification."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_stack: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_stack.append(tag.lower())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._skip_stack:
            text = normalize_space(data)
            if text:
                self._parts.append(text)

    def text(self) -> str:
        return normalize_space(" ".join(self._parts))


def default_targets() -> list[SourceTarget]:
    return [
        SourceTarget(
            name="微博搜索",
            category="social",
            url_template="https://s.weibo.com/weibo?q={keyword}",
            notes="公开搜索页；常见登录/验证码/风控限制。",
        ),
        SourceTarget(
            name="微博热搜",
            category="social",
            url_template="https://s.weibo.com/top/summary?cate=realtimehot",
            notes="公开热搜页；可作为舆情热点发现入口。",
        ),
        SourceTarget(
            name="小红书搜索",
            category="social",
            url_template="https://www.xiaohongshu.com/search_result?keyword={keyword}",
            notes="公开搜索页；高度依赖前端渲染和登录态。",
        ),
        SourceTarget(
            name="小红书发现页",
            category="social",
            url_template="https://www.xiaohongshu.com/explore",
            notes="公开发现页；高度依赖前端渲染和登录态。",
        ),
        SourceTarget(
            name="知乎搜索",
            category="social",
            url_template="https://www.zhihu.com/search?q={keyword}&type=content",
            notes="公开搜索页；可能返回登录页或动态渲染内容。",
        ),
        SourceTarget(
            name="知乎热榜",
            category="social",
            url_template="https://www.zhihu.com/hot",
            notes="公开热榜页；可作为舆情热点发现入口。",
        ),
        SourceTarget(
            name="百度贴吧搜索",
            category="forum",
            url_template="https://tieba.baidu.com/f/search/res?ie=utf-8&qw={keyword}",
            notes="公开搜索页；适合作为第一版论坛数据源候选。",
        ),
        SourceTarget(
            name="百度贴吧主题吧",
            category="forum",
            url_template="https://tieba.baidu.com/f?kw={keyword}&ie=utf-8",
            notes="公开贴吧页面；用于测试主题讨论页可访问性。",
        ),
        SourceTarget(
            name="B站搜索",
            category="video",
            url_template="https://search.bilibili.com/all?keyword={keyword}",
            notes="公开搜索页；用于测试视频平台舆情入口。",
        ),
        SourceTarget(
            name="百度新闻搜索",
            category="news",
            url_template="https://news.baidu.com/ns?word={keyword}&tn=news&from=news",
            notes="公开新闻搜索；适合补充权威媒体报道。",
        ),
        SourceTarget(
            name="澎湃新闻搜索",
            category="news",
            url_template="https://www.thepaper.cn/searchResult.jsp?keyword={keyword}",
            notes="新闻站搜索页；用于测试正文/列表可解析性。",
        ),
        SourceTarget(
            name="人民网搜索",
            category="news",
            url_template="http://search.people.cn/s?keyword={keyword}",
            notes="新闻站搜索页；用于测试新闻源可采集性。",
        ),
    ]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def extract_visible_text(content: bytes, content_type: str) -> str:
    text = decode_bytes(content)
    if "xml" in content_type.lower() or text.lstrip().startswith("<?xml"):
        return normalize_space(re.sub(r"<[^>]+>", " ", text))

    parser = VisibleTextParser()
    parser.feed(text)
    return parser.text()


def decode_bytes(content: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def classify_result(status_code: int | None, text: str, error: str) -> tuple[bool, str]:
    lowered = text.lower()

    if status_code is None:
        return False, "network_error"
    if status_code in {401, 403, 429}:
        return False, "blocked_or_rate_limited"
    if status_code >= 500:
        return False, "server_error"
    if status_code >= 400:
        return False, "http_error"
    if error:
        return False, "parse_error"
    if any(hint.lower() in lowered for hint in BLOCK_HINTS):
        return False, "login_or_verification_required"
    if any(re.search(pattern, text) for pattern in NO_RESULT_PATTERNS):
        return False, "no_search_results"
    if len(text) < 120:
        return False, "too_little_text"
    return True, "public_content_accessible"


def probe_target(target: SourceTarget, keyword: str, timeout: int) -> ProbeResult:
    url = target.url(keyword)
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        },
    )

    status_code: int | None = None
    content_type = ""
    body = b""
    error = ""

    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = response.status
            content_type = response.headers.get("Content-Type", "")
            body = response.read(512_000)
    except HTTPError as exc:
        status_code = exc.code
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        body = exc.read(128_000)
        error = str(exc)
    except URLError as exc:
        error = str(exc.reason)
    except TimeoutError as exc:
        error = str(exc)

    text = ""
    if body:
        try:
            text = extract_visible_text(body, content_type)
        except Exception as exc:  # pragma: no cover - defensive probe path
            error = f"{error}; parse failed: {exc}".strip("; ")

    ok, classification = classify_result(status_code, text, error)
    sample = text[:220]

    return ProbeResult(
        name=target.name,
        category=target.category,
        url=url,
        status_code=status_code,
        ok=ok,
        classification=classification,
        content_type=content_type,
        bytes_received=len(body),
        text_chars=len(text),
        sample=sample,
        error=error,
        notes=target.notes,
    )


def run_probe(
    targets: Iterable[SourceTarget],
    keyword: str,
    timeout: int,
    delay: float,
) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    for index, target in enumerate(targets):
        if index:
            time.sleep(delay)
        results.append(probe_target(target, keyword, timeout))
    return results


def write_json(path: str, results: list[ProbeResult]) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump([asdict(result) for result in results], file, ensure_ascii=False, indent=2)


def write_csv(path: str, results: list[ProbeResult]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def print_table(results: list[ProbeResult]) -> None:
    print("name\tstatus\tok\tclassification\tchars\terror")
    for result in results:
        print(
            f"{result.name}\t{result.status_code}\t{result.ok}\t"
            f"{result.classification}\t{result.text_chars}\t{result.error}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe public Chinese web sources.")
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD, help="Search keyword.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--json-out", default="crawl_probe_results.json")
    parser.add_argument("--csv-out", default="crawl_probe_results.csv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = run_probe(default_targets(), args.keyword, args.timeout, args.delay)
    print_table(results)
    if results:
        write_json(args.json_out, results)
        write_csv(args.csv_out, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
