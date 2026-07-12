# Trend Repair And Crawler Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the complete event lifecycle predictor, unblock the Flask backend test suite, and validate every crawler platform required by `docs/爬虫模块设计方案.md` with low-volume real requests.

**Architecture:** Keep lifecycle prediction as a deterministic pure module consumed by `event_service.py`. Keep paid/live crawler checks outside the normal pytest suite in a dedicated diagnostic script, while adapter response-shape regressions remain in mocked unit tests. Fix only project-controlled failures; report authentication, quota, network, and platform restrictions without masking them.

**Tech Stack:** Python 3, Flask, pytest, requests, SQLAlchemy, existing crawler registry and preprocessing pipeline.

---

## File Map

- Modify `backend/app/analysis/trend_predictor.py`: lifecycle thresholds, smoothing, growth rates, stage classification and transition points.
- Modify `backend/tests/test_trend_predictor.py`: add missing edge-case coverage when required by the approved design.
- Create `tools/validate_live_crawlers.py`: safe, low-volume live adapter validator with secret-redacted output.
- Modify `tests/test_public_crawl_probe.py` or create `tests/test_validate_live_crawlers.py`: offline tests for validator classification and output contracts.
- Modify crawler adapters under `backend/app/crawler/` only when a live response proves a project-controlled request or parsing defect.
- Modify `backend/tests/test_crawler_adapters.py` for every adapter regression discovered from live responses.
- Create `crawl_live_validation_results.json`: sanitized validation evidence without credentials or authorization headers.
- Update `docs/crawler_acquisition_plan.md` only if verified platform behavior differs materially from current documentation.

### Task 1: Establish The Lifecycle Predictor Red Baseline

**Files:**
- Test: `backend/tests/test_trend_predictor.py`
- Inspect: `backend/app/services/event_service.py`
- Inspect: `项目需求规格说明书.md`

- [ ] **Step 1: Run the existing lifecycle test file**

Run:

```powershell
python -m pytest -q backend/tests/test_trend_predictor.py
```

Expected: collection fails because `LATENT_MAX_DAILY`, `LATENT_MAX_TOTAL`, `WINDOW_SIZE`, `_growth_rate`, `_smooth`, and `get_lifecycle_change_points` are absent.

- [ ] **Step 2: Confirm all consumers and response contracts**

Run:

```powershell
rg -n "predict_lifecycle_stage|get_lifecycle_change_points|lifecycle_stage|change_points" backend/app backend/tests
```

Expected: `event_service.py` imports both public functions and serializes the stage and transition points.

- [ ] **Step 3: Add focused edge cases before implementation**

Add these tests to `backend/tests/test_trend_predictor.py` if equivalent coverage is absent:

```python
def test_negative_counts_are_treated_as_zero(self):
    self.assertEqual(predict_lifecycle_stage([-5, -1, 0]), "潜伏期")

def test_change_points_ignore_extra_dates(self):
    points = get_lifecycle_change_points([3, 4], ["d1", "d2", "d3"])
    self.assertIsInstance(points, list)
```

- [ ] **Step 4: Run the test and verify RED**

Run:

```powershell
python -m pytest -q backend/tests/test_trend_predictor.py
```

Expected: failure remains attributable to the missing lifecycle implementation.

### Task 2: Implement Deterministic Lifecycle Prediction

**Files:**
- Modify: `backend/app/analysis/trend_predictor.py`
- Test: `backend/tests/test_trend_predictor.py`

- [ ] **Step 1: Define configuration constants and normalization**

Implement integer constants for the approved first-version rules:

```python
WINDOW_SIZE = 3
LATENT_MAX_DAILY = 10
LATENT_MAX_TOTAL = 30
PEAK_MIN_DAILY = 80
GROWTH_RATE_MIN = 0.30
PEAK_STABLE_RATE = 0.10
DECLINE_FROM_PEAK = 0.50
DECLINE_CONSECUTIVE_DAYS = 3
```

Normalize every count with `max(0.0, float(value))`.

- [ ] **Step 2: Implement smoothing and growth helpers**

Implement `_smooth(values, window=WINDOW_SIZE)` using a centered window and `_growth_rate(values)` with these rules:

```python
first rate == 0.0
previous == 0 and current > 0 -> 1.0
previous == 0 and current == 0 -> 0.0
otherwise -> (current - previous) / previous
```

- [ ] **Step 3: Implement four-stage classification**

Use the approved precedence:

```text
empty/low volume -> 潜伏期
clear fall from historical peak or sustained recent decline -> 衰退期
high and stable recent volume -> 高潮期
sustained/meaningful recent growth -> 成长期
otherwise choose 高潮期 for high volume and 潜伏期 for low volume
```

The existing test sequences must classify exactly as asserted.

- [ ] **Step 4: Implement transition point extraction**

Return a list of dictionaries shaped as:

```python
{
    "date": dates[index],
    "from_stage": previous_stage,
    "to_stage": current_stage,
    "index": index,
}
```

Only process `min(len(daily_counts), len(dates))` items and return an empty list for fewer than two aligned points.

- [ ] **Step 5: Run lifecycle tests and verify GREEN**

Run:

```powershell
python -m pytest -q backend/tests/test_trend_predictor.py
```

Expected: all lifecycle tests pass.

- [ ] **Step 6: Verify Flask creation and dependent event imports**

Run:

```powershell
@'
import sys
sys.path.insert(0, 'backend')
from app import create_app
app = create_app()
print(app.url_map)
'@ | python -
```

Expected: exit code 0 and registered `/api/events` routes.

### Task 3: Run Backend Regression And Isolate Remaining Failures

**Files:**
- Modify only files directly implicated by fresh failures.
- Test the matching file under `backend/tests/` before changing production code.

- [ ] **Step 1: Run the complete offline backend test suite**

Run:

```powershell
python -m pytest -q backend/tests tests
```

Expected: no trend-predictor import/collection errors. Record any remaining failures by root cause.

- [ ] **Step 2: For each project-controlled failure, create or retain a focused failing test**

Run the smallest failing node, for example:

```powershell
python -m pytest -q backend/tests/test_crawler_api.py::CrawlerApiTest::test_keyword_search_runs_sample_pipeline_and_exposes_task
```

Expected: a deterministic failure demonstrating the specific defect.

- [ ] **Step 3: Apply one minimal fix per root cause**

Do not combine unrelated refactors. Re-run the focused test after every fix.

- [ ] **Step 4: Re-run the complete offline suite**

Run:

```powershell
python -m pytest -q backend/tests tests
```

Expected: zero failures before live API testing begins.

### Task 4: Build A Secret-Safe Live Crawler Validator

**Files:**
- Create: `tools/validate_live_crawlers.py`
- Create: `tests/test_validate_live_crawlers.py`

- [ ] **Step 1: Write validator unit tests first**

Tests must cover:

```python
def test_result_serialization_never_contains_secret_values(): ...
def test_empty_success_is_distinct_from_success_with_documents(): ...
def test_auth_and_quota_errors_are_classified_without_response_body_dump(): ...
def test_document_contract_requires_platform_title_source_type_and_raw_json(): ...
```

Use fake adapters and fake exceptions; do not access the network.

- [ ] **Step 2: Run validator tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_validate_live_crawlers.py
```

Expected: import failure because the validator does not exist.

- [ ] **Step 3: Implement the live validator**

The script must:

- insert `backend` into `sys.path`;
- load `Config` and `build_crawler_registry`;
- validate `weibo_hot`, `weibo`, `zhihu_hot`, `zhihu`, `bilibili`, `xiaohongshu`, `baidu_hot`, and `baidu`;
- use keyword `人工智能` for search platforms;
- request the minimum supported limit;
- validate `RawDocument` fields;
- run at most one returned document through `preprocess_document`;
- classify `AUTH_ERROR`, `QUOTA_ERROR`, `REMOTE_CHANGED`, `PLATFORM_BLOCKED`, `NETWORK_ERROR`, and `CODE_ERROR`;
- never include environment values, authorization headers, or full remote bodies;
- write sanitized JSON to `crawl_live_validation_results.json`;
- exit nonzero when any required platform has a project-controlled code failure.

- [ ] **Step 4: Run validator unit tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_validate_live_crawlers.py
```

Expected: all validator tests pass without network access.

### Task 5: Validate Free/Public Platforms First

**Files:**
- Potentially modify: `backend/app/crawler/weibo.py`
- Potentially modify: `backend/app/crawler/bilibili.py`
- Test: `backend/tests/test_crawler_adapters.py`
- Output: `crawl_live_validation_results.json`

- [ ] **Step 1: Run only Weibo hot and Bilibili live checks**

Run:

```powershell
python tools/validate_live_crawlers.py --platform weibo_hot --platform bilibili --keyword 人工智能
```

Expected: sanitized status, document counts and preprocessing results.

- [ ] **Step 2: If a response shape changed, add a failing fixture test**

Copy only the minimum sanitized response fields into `backend/tests/test_crawler_adapters.py`; remove IDs, cookies, headers and unrelated content.

Run the focused test and confirm failure before modifying the adapter.

- [ ] **Step 3: Apply the minimal request or parser fix**

Preserve the `RawDocument` contract and existing `HttpClient` safety restrictions.

- [ ] **Step 4: Re-run mocked and live checks**

Run:

```powershell
python -m pytest -q backend/tests/test_crawler_adapters.py
python tools/validate_live_crawlers.py --platform weibo_hot --platform bilibili --keyword 人工智能
```

Expected: unit tests pass; live output contains no `CODE_ERROR` for these platforms.

### Task 6: Validate Zhihu Official API

**Files:**
- Potentially modify: `backend/app/crawler/zhihu.py`
- Test: `backend/tests/test_crawler_adapters.py`
- Output: `crawl_live_validation_results.json`

- [ ] **Step 1: Run low-volume Zhihu search and hot checks**

Run:

```powershell
python tools/validate_live_crawlers.py --platform zhihu --platform zhihu_hot --keyword 人工智能
```

Expected: either documents/valid empty results, or a classified external authentication/product error.

- [ ] **Step 2: Add a sanitized failing response-shape test for project-controlled defects**

Run the focused test and verify RED.

- [ ] **Step 3: Fix request construction or parsing and verify**

Run:

```powershell
python -m pytest -q backend/tests/test_crawler_adapters.py
python tools/validate_live_crawlers.py --platform zhihu --platform zhihu_hot --keyword 人工智能
```

Expected: no project-controlled `CODE_ERROR`.

### Task 7: Validate TikHub Weibo And Xiaohongshu

**Files:**
- Potentially modify: `backend/app/crawler/tikhub.py`
- Test: `backend/tests/test_crawler_adapters.py`
- Output: `crawl_live_validation_results.json`

- [ ] **Step 1: Run one low-volume request per paid platform**

Run:

```powershell
python tools/validate_live_crawlers.py --platform weibo --platform xiaohongshu --keyword 人工智能
```

Expected: at most the configured minimal paid calls, with sanitized output.

- [ ] **Step 2: Distinguish code defects from product permission failures**

Treat wrong endpoint or parser assumptions as code defects. Treat invalid key, insufficient balance, or endpoint not included in the subscription as external limitations.

- [ ] **Step 3: Add a failing sanitized fixture test before any adapter fix**

Run the focused test and verify RED.

- [ ] **Step 4: Apply the minimal adapter fix and verify**

Run:

```powershell
python -m pytest -q backend/tests/test_crawler_adapters.py
python tools/validate_live_crawlers.py --platform weibo --platform xiaohongshu --keyword 人工智能
```

Expected: no project-controlled `CODE_ERROR`; external restrictions remain accurately classified.

### Task 8: Validate Qianfan Baidu Search And Trending

**Files:**
- Potentially modify: `backend/app/crawler/qianfan.py`
- Test: `backend/tests/test_crawler_adapters.py`
- Output: `crawl_live_validation_results.json`

- [ ] **Step 1: Run one low-volume request per Qianfan endpoint**

Run:

```powershell
python tools/validate_live_crawlers.py --platform baidu --platform baidu_hot --keyword 人工智能
```

Expected: sanitized search and trending statuses.

- [ ] **Step 2: Add failing fixture tests for any request or response mismatch**

Verify RED before modifying `qianfan.py`.

- [ ] **Step 3: Apply the minimal adapter fix and verify**

Run:

```powershell
python -m pytest -q backend/tests/test_crawler_adapters.py
python tools/validate_live_crawlers.py --platform baidu --platform baidu_hot --keyword 人工智能
```

Expected: no project-controlled `CODE_ERROR`; authentication and quota restrictions are reported honestly.

### Task 9: Final Regression And Evidence Review

**Files:**
- Review: `crawl_live_validation_results.json`
- Review: all changed source and test files
- Potentially modify: `docs/crawler_acquisition_plan.md`

- [ ] **Step 1: Run the complete backend suite fresh**

Run:

```powershell
python -m pytest -q backend/tests tests
```

Expected: zero failures.

- [ ] **Step 2: Run the complete low-volume live validation once**

Run:

```powershell
python tools/validate_live_crawlers.py --all --keyword 人工智能
```

Expected: every required platform has a sanitized result; no platform has an unresolved `CODE_ERROR`.

- [ ] **Step 3: Inspect secrets and repository diff**

Run:

```powershell
git diff --check
git status --short
rg -n "Authorization|Bearer |TIKHUB_API_KEY|QIANFAN_API_KEY|ZHIHU_ACCESS_SECRET|LLM_API_KEY" crawl_live_validation_results.json tools/validate_live_crawlers.py
```

Expected: result JSON contains no credentials; code only references environment variable names, never values.

- [ ] **Step 4: Summarize platform status accurately**

Report for each platform:

```text
registered / live request / documents / preprocessing / code fixes / external limitation
```

Do not mark authentication, quota or platform restrictions as successful crawling.

