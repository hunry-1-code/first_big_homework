# Daily Top10 Hotspots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a fast, durable and explainable daily Top10 endpoint sourced from direct platform hot lists, with asynchronous enrichment into formal events.

**Architecture:** Store raw hot-list runs/items separately from formal Events. Normalize and merge multi-source titles, fuse ranks with Reciprocal Rank Fusion, expose cached Top10 immediately, and enqueue downstream enrichment independently per item.

**Tech Stack:** Flask, SQLAlchemy, APScheduler, existing crawler registry/task leases, pytest, SQLite/MySQL migrations.

---

### Task 1: Implement pure hot-title normalization and RRF ranking

**Files:**
- Create: `backend/app/analysis/daily_hot.py`
- Create: `backend/tests/test_daily_hot.py`

- [x] **Step 1: Write failing pure algorithm tests**

Cover punctuation/hashtag normalization, same-title merging, independent source contribution, stable tie-breaking and result limiting.

```python
items = [
    HotRankItem("weibo_hot", 1, "#某地暴雨#"),
    HotRankItem("baidu_hot", 3, "某地暴雨"),
    HotRankItem("zhihu_hot", 1, "另一事件"),
]
ranked = fuse_hot_rankings(items, rrf_k=60)
self.assertEqual(ranked[0].normalized_title, "某地暴雨")
self.assertEqual(ranked[0].source_ranks, {"weibo_hot": 1, "baidu_hot": 3})
```

- [x] **Step 2: Run and verify RED**

```powershell
python -m pytest backend/tests/test_daily_hot.py -q
```

- [x] **Step 3: Implement dataclasses and fusion**

```python
@dataclass(frozen=True)
class HotRankItem:
    source: str
    rank: int
    title: str
    source_url: str | None = None
    raw: dict = field(default_factory=dict)
```

Normalize Unicode, hashtags, repeated whitespace and trailing heat labels. Calculate `sum(1 / (rrf_k + rank))`; one source contributes once per normalized item. Sort by score descending, source count descending, best rank ascending, normalized title ascending.

- [x] **Step 4: Run tests and commit**

Commit pure algorithm and tests.

### Task 2: Add daily hot persistence models and migrations

**Files:**
- Create: `backend/app/models/daily_hot.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/20260713_daily_hot.sql`
- Create: `backend/migrations/migrate_daily_hot.py`
- Create: `backend/tests/test_daily_hot_migration.py`

- [x] **Step 1: Write failing schema tests**

Assert `db.create_all()` includes `daily_hot_run` and `daily_hot_item`, unique run/source/date constraints, JSON source ranks/errors and nullable event/task references.

- [x] **Step 2: Run and verify RED**

- [x] **Step 3: Define models**

`DailyHotRun` fields: id, run_date, status, available_sources, failed_sources, errors, item_count, config_hash, created_at, completed_at.

`DailyHotItem` fields: id, run_id, normalized_key, title, fused_score, rank, source_ranks, source_payloads, first_seen_at, last_seen_at, enrichment_status, event_id, analysis_task_id, error_code, error_message.

- [x] **Step 4: Write idempotent SQL/Python migrations**

Support MySQL production migration and SQLite model creation tests. Do not mutate existing Event rows.

- [x] **Step 5: Run migration tests and commit**

### Task 3: Collect direct platform hot lists with failure isolation

**Files:**
- Create: `backend/app/services/daily_hot_service.py`
- Create: `backend/tests/test_daily_hot_service.py`

- [ ] **Step 1: Write failing fake-registry tests**

Use fake `weibo_hot`, `baidu_hot`, `zhihu_hot` crawlers. Assert two successful sources still produce a run when the third raises `CrawlerError`, and secrets are not stored in errors.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Implement collection**

For each configured source, call one hot-mode request with the configured limit. Read rank from `raw_json.rank` or stable list position. Convert RawDocument to `HotRankItem`, fuse, persist top N and source diagnostics in one transaction.

- [ ] **Step 4: Implement run reuse**

Reuse a successful fresh run within `DAILY_HOT_TTL_SECONDS`; create a new attempt when the previous run failed or is stale.

- [ ] **Step 5: Run tests and commit**

### Task 4: Add Top10 query and administrator refresh APIs

**Files:**
- Modify: `backend/app/api/hotspots.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Create: `backend/tests/test_daily_hot_api.py`

- [ ] **Step 1: Write failing API tests**

Cover login requirement, default limit 10, limit validation, empty state, stale cached state, partial source failure and administrator-only refresh.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Add configuration**

```python
DAILY_HOT_SOURCES = ["weibo_hot", "baidu_hot", "zhihu_hot"]
DAILY_HOT_SOURCE_LIMIT = 30
DAILY_HOT_RESULT_LIMIT = 10
DAILY_HOT_RRF_K = 60
DAILY_HOT_TTL_SECONDS = 900
```

Parse source list from environment and bound numeric values.

- [ ] **Step 4: Add endpoints**

```python
@hotspots_bp.get("/today")
@login_required
def today_hotspots(): ...

@hotspots_bp.post("/today/refresh")
@admin_required
def refresh_today_hotspots(): ...
```

Use the common `{code,message,data}` response. Return date, generated time, stale flag, source diagnostics and items.

- [ ] **Step 5: Run API tests and commit**

### Task 5: Add a leased background refresh job

**Files:**
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/app/tasks/runner.py`
- Modify: `backend/app/tasks/scheduler.py`
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/tests/test_jobs.py`
- Create or modify: `backend/tests/test_task_recovery.py`

- [ ] **Step 1: Write failing job and recovery tests**

Assert a `daily_hot` task is claimed once, updates progress, persists a run, survives one source failure and is discoverable by recovery registry.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Implement `daily_hot_job(task_id)`**

Load sources/limits from task payload, call the service, update progress at source collection, fusion and persistence boundaries, then store run ID and counts.

- [ ] **Step 4: Register recovery and scheduler**

Add `daily_hot` to the job registry. Scheduler creates or reuses an equivalent task every configured interval. Use the configured system/admin actor and fail explicitly if no valid actor exists; do not create an unowned Task because `created_by` is non-null.

- [ ] **Step 5: Run task tests and commit**

### Task 6: Enqueue independent enrichment for Top10 items

**Files:**
- Modify: `backend/app/services/daily_hot_service.py`
- Modify: `backend/app/tasks/jobs.py`
- Create: `backend/tests/test_daily_hot_enrichment.py`

- [ ] **Step 1: Write failing isolation tests**

Create three items; make one enrichment fail. Assert the other two progress and the failed item stores a sanitized error without failing the DailyHotRun.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Implement item enrichment state transitions**

Allowed states: `pending`, `running`, `completed`, `failed`, `no_event`. Use the existing keyword crawl → content analysis → aggregation chain. Link `event_id` only after a formal event is published or matched.

- [ ] **Step 4: Ensure idempotence**

Do not enqueue another active task for the same item and normalized keyword. Reuse compatible search cache results when present.

- [ ] **Step 5: Run tests and commit**

### Task 7: Validate existing formal-hotspot compatibility

**Files:**
- Modify: `backend/tests/test_hotspot_service.py`
- Modify: `backend/tests/test_daily_hot_api.py`

- [ ] **Step 1: Add compatibility tests**

Assert `GET /api/hotspots` continues returning analyzed formal events, while `/today` returns raw/fused daily hot items with optional event IDs. The two endpoints must not silently change each other's meaning.

- [ ] **Step 2: Run and fix only demonstrated compatibility issues**

- [ ] **Step 3: Commit if production changes were required**

### Task 8: Run automated and low-volume live validation

**Files:**
- Modify: `tools/validate_live_crawlers.py`
- Create: `tests/daily_hot_live_validation_results.json`
- Modify: `docs/integration_report.md`
- Modify: `docs/后端系统现状与接口说明.md`

- [ ] **Step 1: Run automated Top10 suites**

```powershell
python -m pytest backend/tests/test_daily_hot.py backend/tests/test_daily_hot_migration.py backend/tests/test_daily_hot_service.py backend/tests/test_daily_hot_api.py backend/tests/test_daily_hot_enrichment.py backend/tests/test_jobs.py backend/tests/test_hotspot_service.py -q
```

- [ ] **Step 2: Run the full suite**

```powershell
python -m pytest backend/tests tests -q
```

Expected: zero automated failures before live validation.

- [ ] **Step 3: Run secret-safe live hot-list validation**

Use `backend/.env` without printing it:

```powershell
python tools\validate_live_crawlers.py --platform weibo_hot --platform baidu_hot --platform zhihu_hot --keyword 舆情 --output tests\daily_hot_live_validation_results.json
```

Then call the refresh endpoint or service with the smallest supported limits. Classify authentication, quota, network, platform blocking and empty responses separately.

- [ ] **Step 4: Update documentation with exact results**

Record available/failed sources, fused item count, timestamps, automated test count and known external limitations. Never include keys or Authorization values.

- [ ] **Step 5: Commit**

Commit validator, safe result artifact and documents after inspecting for secrets.
