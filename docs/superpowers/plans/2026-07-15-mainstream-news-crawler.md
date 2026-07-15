# Mainstream News Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one selectable `mainstream_news` platform that low-frequency crawls People.cn, 36Kr, The Paper, InfoQ, and SSPAI, persists concrete source IDs, and best-effort collects verified public comments.

**Architecture:** A `MainstreamNewsCrawler` owns five focused child adapters and allocates at most five documents to each source. People.cn uses the public endpoint currently called by its official search page, with its official RSS as a freshness-checked fallback; the other four sources share an improved RSS adapter. A separate news-comment dispatcher supports only the publicly verified The Paper and SSPAI endpoints and returns explicit `success`, `empty`, `unsupported`, or `failed` outcomes without failing article ingestion.

**Tech Stack:** Python 3, Flask, requests, ElementTree, trafilatura, SQLAlchemy, unittest/pytest, Vue 3, TypeScript, pnpm.

---

## File map

- Create `backend/app/crawler/people_news.py`: People.cn official-search adapter and stale RSS fallback.
- Create `backend/app/crawler/mainstream_news.py`: five-source quota allocation, fault isolation, URL de-duplication, and source statistics.
- Create `backend/app/crawler/news_comments.py`: SSPAI/The Paper public comment adapters and status dispatcher.
- Modify `backend/app/crawler/http.py`: deterministic XML/text byte decoding.
- Modify `backend/app/crawler/rss.py`: request headers, title-or-summary filtering, strict limits, injectable article extraction, and fallback behavior.
- Modify `backend/app/crawler/factory.py`: construct and register only the aggregate selectable platform.
- Modify `backend/app/services/crawl_service.py`: count accepted aggregate documents by their concrete `news_*` source IDs.
- Modify `backend/app/tasks/jobs.py`: enrich `news_*` documents with at most ten comments and expose status/count summaries.
- Modify `backend/app/api/crawler.py`: expose `mainstream_news`, not its five internal IDs.
- Modify `backend/app/services/api_contract_service.py`: add aggregate and concrete source display names.
- Modify `frontend/src/constants/platforms.ts`: replace the individual RSS card with one mainstream-news card and source-name mappings.
- Create `backend/tests/test_mainstream_news_crawler.py`: adapter, aggregation, and comment unit tests.
- Modify `backend/tests/test_crawler_core.py`, `backend/tests/test_crawler_api.py`, and `backend/tests/test_jobs.py`: regression and integration coverage.

### Task 1: Harden HTTP text and RSS behavior

**Files:**
- Modify: `backend/app/crawler/http.py`
- Modify: `backend/app/crawler/rss.py`
- Modify: `backend/tests/test_crawler_core.py`
- Modify: `backend/tests/test_crawler_adapters.py`

- [ ] **Step 1: Write failing decoding and RSS tests**

Add tests proving that UTF-8 XML is decoded from response bytes even when the server advertises ISO-8859-1, feed requests include browser/XML headers, keywords match either title or summary, article extraction failure falls back to a sufficiently long summary, and results never exceed `request.limit`.

```python
def test_http_client_decodes_utf8_xml_despite_wrong_response_encoding(self):
    response = FakeResponse(200, text="")
    response.content = "<?xml version='1.0' encoding='utf-8'?><rss><title>人民网</title></rss>".encode("utf-8")
    response.encoding = "ISO-8859-1"
    client = HttpClient(session=FakeSession([response]), allowed_hosts={"example.com"}, resolver=lambda _: ["93.184.216.34"])
    self.assertIn("人民网", client.get_text("https://example.com/feed.xml", prefer_xml=True))

def test_rss_matches_summary_and_strictly_limits_results(self):
    crawler = RssCrawler(StubClient(RSS_WITH_THREE_SUMMARY_MATCHES), "https://example.com/feed.xml", article_extractor=lambda _: None)
    rows = crawler.crawl(CrawlRequest("rss", keyword="人工智能", limit=2))
    self.assertEqual(len(rows), 2)
    self.assertTrue(all("人工智能" in row.raw_content for row in rows))
    self.assertEqual(crawler.client.calls[0][2]["headers"]["Accept"], "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
cd backend
python -m pytest tests/test_crawler_core.py tests/test_crawler_adapters.py -q
```

Expected: failures because `prefer_xml`, request headers, `article_extractor`, summary matching, and strict limiting are not implemented.

- [ ] **Step 3: Implement minimal decoding and RSS changes**

Implement `HttpClient.get_text(..., prefer_xml=False)` so XML mode decodes bytes using BOM/XML declaration first and UTF-8 fallback. Update `RssCrawler` to accept `article_extractor`, request the feed with a normal browser `User-Agent` and XML `Accept`, filter on normalized title plus summary, extract only selected rows sequentially, reject empty/very short fallback text, and stop at the requested limit.

```python
text = self.client.get_text(
    self.feed_url,
    prefer_xml=True,
    headers={"User-Agent": USER_AGENT, "Accept": RSS_ACCEPT},
)
candidate_text = f"{title}\n{summary}"
if keyword_parts and not any(part.casefold() in candidate_text.casefold() for part in keyword_parts):
    continue
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

### Task 2: Add the People.cn search adapter

**Files:**
- Create: `backend/app/crawler/people_news.py`
- Create: `backend/tests/test_mainstream_news_crawler.py`

- [ ] **Step 1: Write failing People.cn mapping and fallback tests**

Test the exact official-page payload and headers, mapping of `id`, `title`, `url`, `inputTime`, `originName`, and `content`, HTML-tag removal, limit five, and fallback rejection of RSS entries older than the configured freshness window.

```python
def test_people_search_uses_official_payload_and_maps_records(self):
    crawler = PeopleNewsCrawler(client, rss_fallback=None, article_extractor=lambda _: None)
    rows = crawler.crawl(CrawlRequest("news_people", keyword="人工智能", limit=5))
    method, url, kwargs = client.calls[0]
    assert method == "POST"
    assert url == "http://search.people.cn/search-platform/front/search"
    assert kwargs["json"]["key"] == "人工智能"
    assert kwargs["json"]["page"] == 1
    assert kwargs["json"]["limit"] == 5
    assert rows[0].platform == "news_people"
    assert rows[0].source_article_id == "1000040756993"
    assert "<em>" not in rows[0].title
```

- [ ] **Step 2: Run test and verify RED**

Run:

```powershell
cd backend
python -m pytest tests/test_mainstream_news_crawler.py -q
```

Expected: import failure because `PeopleNewsCrawler` does not exist.

- [ ] **Step 3: Implement People.cn search and RSS fallback**

Post one page with:

```python
payload = {
    "key": keyword,
    "page": 1,
    "limit": min(5, request.limit),
    "hasTitle": True,
    "hasContent": True,
    "isFuzzy": True,
    "type": 0,
    "sortType": 2,
    "startTime": 0,
    "endTime": 0,
}
```

Validate `code == "0"`, map `data.records`, prefer extracted article text when available, otherwise use cleaned `contentOriginal`/`content`, and invoke a freshness-filtered official RSS crawler only when the search request fails or yields no usable rows.

- [ ] **Step 4: Run test and verify GREEN**

Run the Step 2 command. Expected: People.cn tests pass.

### Task 3: Add five-source aggregation

**Files:**
- Create: `backend/app/crawler/mainstream_news.py`
- Modify: `backend/app/crawler/factory.py`
- Modify: `backend/app/services/crawl_service.py`
- Modify: `backend/tests/test_mainstream_news_crawler.py`
- Modify: `backend/tests/test_crawl_service.py`

- [ ] **Step 1: Write failing aggregation tests**

Cover quota examples `10 -> 2 each`, `20 -> 4 each`, `50 -> 5 each`, partial-source failure, URL de-duplication, concrete source IDs, total limit, and source statistics.

```python
def test_mainstream_news_allocates_caps_and_isolates_failures():
    crawler = MainstreamNewsCrawler([
        FakeSource("news_people", 5),
        FailingSource("news_36kr"),
        FakeSource("news_thepaper", 5),
        FakeSource("news_infoq", 5),
        FakeSource("news_sspai", 5),
    ])
    rows = crawler.crawl(CrawlRequest("mainstream_news", keyword="人工智能", limit=20))
    assert len(rows) == 16
    assert crawler.last_source_counts == {
        "news_people": 4, "news_36kr": 0, "news_thepaper": 4,
        "news_infoq": 4, "news_sspai": 4,
    }
    assert {row.platform for row in rows} <= set(crawler.last_source_counts)
```

- [ ] **Step 2: Run test and verify RED**

Run `python -m pytest tests/test_mainstream_news_crawler.py -q`. Expected: missing aggregate crawler.

- [ ] **Step 3: Implement the aggregate and registry construction**

Use fixed source order `people, 36kr, thepaper, infoq, sspai`; calculate `base, remainder = divmod(min(request.limit, 25), 5)`, give the first `remainder` sources one extra slot, cap every slot at five, catch each child exception independently, de-duplicate normalized URLs, and register only `mainstream_news` as selectable. When `CrawlService` accepts aggregate documents, increment `platform_counts` using `document.platform` so the task result reports the five real sites. Construct RSS sources with:

```python
NEWS_FEEDS = {
    "news_36kr": "https://36kr.com/feed",
    "news_thepaper": "https://m.thepaper.cn/rss_news",
    "news_infoq": "https://www.infoq.cn/feed",
    "news_sspai": "https://sspai.com/feed",
}
```

- [ ] **Step 4: Run aggregation and existing registry tests**

Run:

```powershell
python -m pytest tests/test_mainstream_news_crawler.py tests/test_crawler_adapters.py tests/test_crawl_service.py -q
```

Expected: all pass.

### Task 4: Add verified public news comments without blocking articles

**Files:**
- Create: `backend/app/crawler/news_comments.py`
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/tests/test_mainstream_news_crawler.py`
- Modify: `backend/tests/test_jobs.py`

- [ ] **Step 1: Write failing comment adapter and job tests**

Test SSPAI article-ID extraction and response mapping, The Paper numeric-ID extraction and response mapping, strict ten-comment caps, `empty`, `unsupported`, and `failed` statuses, stable comment IDs, and that a comment error still leaves the article persisted.

```python
def test_sspai_comments_map_public_response_and_limit_ten(self):
    result = dispatcher.fetch(document, limit=50)
    assert result.status == "success"
    assert len(result.comments) == 10
    assert result.comments[0].platform == "news_sspai"
    assert result.comments[0].source_comment_id == "428733"

def test_people_and_unverified_sources_are_unsupported(self):
    for platform in ("news_people", "news_36kr", "news_infoq"):
        assert dispatcher.fetch(make_document(platform), limit=10).status == "unsupported"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_mainstream_news_crawler.py tests/test_jobs.py -q
```

Expected: missing dispatcher/status types and missing job summary fields.

- [ ] **Step 3: Implement comment dispatcher and job integration**

Use only these verified public reads:

```text
GET https://sspai.com/api/v2/comment/search/page/get?article_id={id}&limit=10&offset=0
GET https://cache.thepaper.cn/commentapi/news/comment/webOneList/{id}
```

Return a result object containing `status`, `comments`, and a sanitized `error`. In `_enrich_article_comments`, cap news sources at ten regardless of the global social-comment limit, persist valid comments, and aggregate per-source summaries such as:

```json
{"news_sspai": {"success": 1, "empty": 0, "unsupported": 0, "failed": 0, "saved": 3}}
```

Do not raise comment failures into the article loop.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: all pass and article counts remain unchanged when comments fail.

### Task 5: Expose one platform card and concrete display names

**Files:**
- Modify: `backend/app/api/crawler.py`
- Modify: `backend/app/services/api_contract_service.py`
- Modify: `backend/tests/test_crawler_api.py`
- Modify: `frontend/src/constants/platforms.ts`

- [ ] **Step 1: Write failing API assertions**

```python
def test_platforms_exposes_only_mainstream_news_for_five_news_sources(self):
    payload = self.client.get("/api/crawler/platforms", headers=self.headers).get_json()["data"]
    assert "mainstream_news" in payload["platforms"]
    for internal in ("news_people", "news_36kr", "news_thepaper", "news_infoq", "news_sspai"):
        assert internal not in payload["platforms"]
        assert internal not in payload["rss"]
```

- [ ] **Step 2: Run API test and verify RED**

Run `python -m pytest tests/test_crawler_api.py -q`. Expected: `mainstream_news` is absent.

- [ ] **Step 3: Implement API and frontend constants**

Add one `SEARCH_PLATFORMS` entry:

```ts
{
  name: "主流新闻网站",
  id: "mainstream_news",
  always: true,
  icon: "ri:newspaper-line",
  color: "#2563eb",
  bg: "#eff6ff"
}
```

Remove the selectable `rss_36kr` card and add `EN_TO_CN` mappings for all five `news_*` IDs. Ensure the discovery API filters internal IDs even if future registry construction exposes them.

- [ ] **Step 4: Run API test and frontend checks**

Run:

```powershell
cd backend
python -m pytest tests/test_crawler_api.py tests/test_contracts.py -q
cd ..\frontend
pnpm typecheck
pnpm build
```

Expected: backend tests, typecheck, and build all exit zero.

### Task 6: Full verification and real low-frequency acceptance crawl

**Files:**
- No production file changes unless a failing verification receives a regression test first.

- [ ] **Step 1: Run focused backend verification**

```powershell
cd backend
python -m pytest tests/test_crawler_core.py tests/test_crawler_adapters.py tests/test_mainstream_news_crawler.py tests/test_crawl_service.py tests/test_crawler_api.py tests/test_jobs.py -q
```

Expected: zero failures.

- [ ] **Step 2: Run the complete backend suite**

```powershell
python -m pytest -q
```

Expected: zero failures. If an unrelated pre-existing failure appears, record the exact test and distinguish it from feature regressions.

- [ ] **Step 3: Restart services with the real environment**

Verify `backend/.env` retains `AUTO_PUBLISH_EVENTS=true`, restart Flask on its configured port, verify the frontend dev server, and call their health/login endpoints. Do not print API keys.

- [ ] **Step 4: Submit one real crawl**

Authenticate with the existing local account and submit:

```json
{"keyword":"人工智能","platforms":["mainstream_news"],"target_count":25,"force":true}
```

Poll the task until success/failure without exceeding normal UI polling frequency.

- [ ] **Step 5: Produce user-verifiable evidence**

Query the local database/API and report:

- task ID and final task status;
- aggregation run ID and published event IDs;
- per-source article counts, each at most five and total at most 25;
- each article ID, concrete platform, title, original URL, publish time, and content length;
- each stored public comment with article ID, concrete platform, source comment ID, author, likes, and text excerpt;
- per-source comment status counts including People.cn `unsupported`;
- the local frontend URLs where the user can inspect the analysis task and event dashboard.

Do not fabricate missing sources or comments; explicitly show zero/empty/unsupported/failed outcomes.
