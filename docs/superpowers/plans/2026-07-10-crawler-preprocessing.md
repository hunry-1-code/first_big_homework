# Crawler And Preprocessing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crawler and preprocessing placeholders with a runnable, testable pipeline that collects authorized public data into one `RawDocument` contract, preserves raw evidence, cleans and scores text, marks duplicates, stores features, and updates background task status.

**Architecture:** Platform adapters depend on one retrying HTTP client and return `RawDocument` values without writing the database. `CrawlService` handles platform selection and count allocation. The preprocessing modules remain pure functions; `pipeline.py` composes them, while a persistence service owns SQLAlchemy writes for articles, snapshots, document features, and processing logs. API endpoints create tasks and submit them to a lightweight in-process runner so HTTP requests return immediately.

**Tech Stack:** Python 3, Flask 3, SQLAlchemy, requests, BeautifulSoup4, trafilatura, readability-lxml, jieba, python-dateutil, APScheduler/thread pool, unittest.

---

### Task 1: Shared Crawler Contract And HTTP Safety

**Files:**
- Modify: `backend/app/crawler/base.py`
- Create: `backend/app/crawler/errors.py`
- Create: `backend/app/crawler/http.py`
- Test: `backend/tests/test_crawler_core.py`

- [ ] **Step 1: Write failing tests for the unified document and retry behavior**

```python
def test_raw_document_preserves_platform_fields():
    document = RawDocument(platform="baidu", source_url="https://example.com/1", title="标题", raw_content="正文")
    assert document.clean_status == "pending"
    assert document.raw_json == {}

def test_http_client_retries_500_then_returns_json():
    session = FakeSession([FakeResponse(500), FakeResponse(200, {"ok": True})])
    assert HttpClient(session=session, sleep=lambda _: None).get_json("https://example.com") == {"ok": True}
    assert session.calls == 2
```

- [ ] **Step 2: Run `python tests/test_crawler_core.py -v` and verify missing classes fail**
- [ ] **Step 3: Implement `RawDocument`, `CrawlRequest`, `CrawlBatch`, `CrawlerError`, URL allow-list checks, timeout handling, retryable 429/5xx errors, and immediate 401/403 failures**
- [ ] **Step 4: Run the crawler core tests and verify they pass**

### Task 2: Platform Adapters And Registry

**Files:**
- Create: `backend/app/crawler/qianfan.py`
- Create: `backend/app/crawler/zhihu.py`
- Create: `backend/app/crawler/weibo.py`
- Create: `backend/app/crawler/bilibili.py`
- Create: `backend/app/crawler/tikhub.py`
- Create: `backend/app/crawler/rss.py`
- Create: `backend/app/crawler/factory.py`
- Modify: `backend/app/crawler/__init__.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_crawler_adapters.py`

- [ ] **Step 1: Write response-mapping tests using local fixtures, never live paid calls**

```python
def test_qianfan_search_maps_reference():
    crawler = QianfanSearchCrawler(client=StubClient({"references": [{"url": "https://n/1", "title": "T", "content": "C", "date": "2026-07-10"}]}), api_key="k")
    result = crawler.crawl(CrawlRequest(platform="baidu", keyword="测试", limit=1))
    assert result[0].source_url == "https://n/1"

def test_bilibili_maps_video_result():
    payload = {"data": {"result": [{"bvid": "BV1", "title": "<em>测试</em>", "description": "简介", "pubdate": 1}]}}
    assert BilibiliCrawler(StubClient(payload)).crawl(CrawlRequest("bilibili", "测试", 1))[0].source_article_id == "BV1"
```

- [ ] **Step 2: Verify adapter tests fail before implementation**
- [ ] **Step 3: Implement verified official endpoints**

```text
Qianfan: POST /v2/ai_search/web_search, GET /v2/tools/baidu_trending
Zhihu: GET /api/v1/content/zhihu_search, GET /api/v1/content/hot_list
Bilibili: GET /x/web-interface/search/type
Weibo public hot list: GET /ajax/side/hotSearch
TikHub: GET weibo/web/fetch_search, GET xiaohongshu/app_v2/search_notes, POST douyin/search/fetch_general_search_v1
RSS: standard RSS/Atom XML
```

- [ ] **Step 4: Register only adapters whose required credentials are configured; keep sample/RSS/public adapters usable without secrets**
- [ ] **Step 5: Run adapter tests and verify all mappings pass**

### Task 3: Crawl Orchestration And API Validation

**Files:**
- Create: `backend/app/services/crawl_service.py`
- Modify: `backend/app/api/crawler.py`
- Modify: `backend/app/services/task_service.py`
- Test: `backend/tests/test_crawl_service.py`

- [ ] **Step 1: Write failing tests for platform allocation, target count limits, and partial failure**

```python
def test_collect_caps_target_at_200_and_single_platform_at_50():
    batch = CrawlService(registry).collect("事件", ["a", "b"], target_count=500)
    assert batch.target_count == 200
    assert max(batch.platform_counts.values()) <= 50

def test_one_platform_failure_does_not_discard_other_results():
    batch = CrawlService(registry_with_one_failure).collect("事件", ["ok", "bad"], 20)
    assert batch.documents
    assert batch.errors[0].platform == "bad"
```

- [ ] **Step 2: Verify the service tests fail**
- [ ] **Step 3: Implement default target 100, maximum 200, per-platform preferred cap 50, result de-duplication by source ID/URL, and per-platform error summaries**
- [ ] **Step 4: Validate `/api/crawler/search` fields (`keyword`, optional `platforms`, optional `target_count`) and store the full task payload**
- [ ] **Step 5: Run service and existing contract tests**

### Task 4: Pure Preprocessing Modules

**Files:**
- Create: `backend/app/preprocessing/result.py`
- Create: `backend/app/preprocessing/normalizer.py`
- Replace: `backend/app/preprocessing/extractor.py`
- Replace: `backend/app/preprocessing/cleaner.py`
- Create: `backend/app/preprocessing/quality.py`
- Create: `backend/app/preprocessing/deduplicator.py`
- Replace: `backend/app/preprocessing/segmenter.py`
- Modify: `backend/app/preprocessing/__init__.py`
- Test: `backend/tests/test_preprocessing.py`

- [ ] **Step 1: Write failing normalization tests**

```python
def test_normalizer_canonicalizes_url_metrics_and_timezone():
    result = normalize_document({"platform": "B站", "url": "HTTPS://EXAMPLE.COM/a?utm_source=x#p", "likes_count": "1.2万", "publish_time": "2026-07-10 08:00:00", "raw_content": "正文"})
    assert result.data["platform"] == "bilibili"
    assert result.data["url"] == "https://example.com/a"
    assert result.data["likes_count"] == 12000
    assert "timezone_assumed" in result.warnings
```

- [ ] **Step 2: Write failing extraction/cleaning tests covering text bypass, BS4 fallback, blocked pages, paragraph preservation, topics, mentions, and template noise**
- [ ] **Step 3: Write failing quality tests for the documented weighted score and quality-level boundaries**
- [ ] **Step 4: Write failing duplicate tests for SHA-256, Jaccard, SimHash, and short-title protection**
- [ ] **Step 5: Write failing segment tests for jieba output, stopword filtering, and sentiment negation preservation**
- [ ] **Step 6: Implement all modules as pure functions returning `success/degraded/failed`, warnings, stable error codes, versions, and data**
- [ ] **Step 7: Run `python tests/test_preprocessing.py -v` and verify the complete module suite passes**

### Task 5: Pipeline And Persistence Models

**Files:**
- Create: `backend/app/preprocessing/pipeline.py`
- Expand: `backend/app/models/article.py`
- Create: `backend/app/models/article_snapshot.py`
- Create: `backend/app/models/document_features.py`
- Create: `backend/app/models/processing_log.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/services/article_pipeline_service.py`
- Test: `backend/tests/test_pipeline.py`
- Test: `backend/tests/test_persistence.py`

- [ ] **Step 1: Write a failing pure pipeline test proving raw data is unchanged and stage errors are attributed correctly**

```python
def test_pipeline_preserves_raw_and_produces_features():
    raw = RawDocument(platform="sample", source_url="sample://1", title="测试", raw_content="这是足够长的测试正文。" * 20, source_type="sample")
    output = preprocess_document(raw)
    assert output.raw_content == raw.raw_content
    assert output.clean_status == "success"
    assert output.features.tfidf_tokens
```

- [ ] **Step 2: Write an in-memory SQLite persistence test for article, first snapshot, features, and processing logs**
- [ ] **Step 3: Implement idempotent pipeline composition and duplicate-candidate input without database access inside algorithm modules**
- [ ] **Step 4: Expand SQLAlchemy models to match the requirement document and implement one transaction per article**
- [ ] **Step 5: Store complete snapshots on first/change observations and interaction-only snapshots otherwise**
- [ ] **Step 6: Run pipeline and persistence tests**

### Task 6: Background Execution And Import Connection

**Files:**
- Replace: `backend/app/tasks/jobs.py`
- Create: `backend/app/tasks/runner.py`
- Modify: `backend/app/api/crawler.py`
- Modify: `backend/app/api/import_data.py`
- Modify: `backend/app/__init__.py`
- Test: `backend/tests/test_jobs.py`

- [ ] **Step 1: Write failing job tests using fake registry and in-memory database**

```python
def test_crawl_job_updates_task_and_persists_documents():
    task = create_task("crawl", 1, {"keyword": "测试", "platforms": ["sample"], "target_count": 1})
    summary = crawl_job(task["id"], registry=sample_registry, app=app)
    assert get_task(task["id"])["status"] == "success"
    assert summary["processed"] == 1
```

- [ ] **Step 2: Verify job tests fail**
- [ ] **Step 3: Implement a bounded thread-pool runner, app-context execution, progress updates, failure summaries, and shutdown cleanup**
- [ ] **Step 4: Submit crawl/import jobs after task creation while keeping API responses immediate**
- [ ] **Step 5: Run job and API contract tests**

### Task 7: Dependencies, Full Verification, And Review

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `docs/framework_overview.md`

- [ ] **Step 1: Add pinned runtime dependencies for HTTP, extraction, parsing, and segmentation**
- [ ] **Step 2: Install dependencies and run all backend tests**

```powershell
python backend/tests/test_contracts.py -v
python backend/tests/test_crawler_core.py -v
python backend/tests/test_crawler_adapters.py -v
python backend/tests/test_crawl_service.py -v
python backend/tests/test_preprocessing.py -v
python backend/tests/test_pipeline.py -v
python backend/tests/test_persistence.py -v
python backend/tests/test_jobs.py -v
python -m unittest discover -s tests -v
```

- [ ] **Step 3: Run `python -m compileall -q backend/app backend/tests tools tests`**
- [ ] **Step 4: Run a Flask test-client smoke test for health, login, crawler task creation, task lookup, and JSON import without contacting paid APIs**
- [ ] **Step 5: Review the diff for secret leakage, raw-content overwrites, unsafe arbitrary URLs, missing timeouts, and unbounded retries**
- [ ] **Step 6: Document implemented adapters, optional credential requirements, and intentionally deferred BGE/live paid API smoke tests**

