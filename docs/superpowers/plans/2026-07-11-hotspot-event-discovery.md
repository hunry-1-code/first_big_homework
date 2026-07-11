# Hotspot Event Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement run-scoped LDA topic discovery, configurable DeepSeek topic naming with deterministic fallback, stable persistence, event heat snapshots/ranking, hot-seed normalization, background task/API entry points, migrations, and automated tests while keeping Single-Pass event aggregation as a separate interface.

**Architecture:** Pure algorithms live under `backend/app/analysis` and do not depend on Flask or SQLAlchemy. `hotspot_service.py` owns run snapshots, persistence, idempotence, LLM orchestration, and the handoff to existing stable `Article.event_id` mappings; if aggregation has not assigned events yet, topic discovery succeeds with an explicit pending warning and no fabricated events. Heat calculation consumes stable event mappings and writes immutable `EventHeatSnapshot` rows.

**Tech Stack:** Python 3, Flask, Flask-SQLAlchemy, scikit-learn LDA, scipy sparse matrices, requests-based OpenAI-compatible DeepSeek API, unittest/pytest-compatible tests, SQLite test database, MySQL 8 migration scripts.

---

## File map

**Create**

- `backend/app/analysis/hotspot_config.py` — immutable topic/heat configuration and hashes.
- `backend/app/analysis/topic_model.py` — small-corpus fallback, LDA candidate training, quality metrics, K selection, document assignments.
- `backend/app/analysis/heat_calculator.py` — time handling, platform-local engagement normalization, core/spread/final heat, eligibility and rank.
- `backend/app/analysis/hot_seed.py` — normalize/merge hot-list titles into expansion queries without treating them as reports.
- `backend/app/models/hotspot.py` — `HotspotRun`, `TopicResult`, `TopicArticleAssignment`, `EventHeatSnapshot`.
- `backend/app/services/hotspot_service.py` — create/reuse runs, rebuild run-scoped documents, persist topics, call naming client, persist heat snapshots.
- `backend/app/api/hotspots.py` — create/list/detail hotspot-run and current ranking endpoints.
- `backend/migrations/20260711_hotspot_discovery.sql` — MySQL tables/indexes and current-event summary columns.
- `backend/migrations/migrate_hotspot_discovery.py` — migration runner.
- `backend/tests/test_hotspot_algorithms.py` — pure topic, heat and seed tests.
- `backend/tests/test_hotspot_service.py` — persistence, idempotence, degradation, task and API tests.
- `backend/tests/test_hotspot_migration.py` — schema and migration tests.

**Modify**

- `backend/app/analysis/topic_classifier.py` — replace stub with structured LLM naming/fallback adapter.
- `backend/app/analysis/hot_detector.py` — retain compatibility export while delegating heat/ranking helpers.
- `backend/app/analysis/__init__.py` — export hotspot public types/functions.
- `backend/app/llm/client.py` — implement OpenAI-compatible chat call with injectable HTTP session and strict failures.
- `backend/app/models/__init__.py` — import hotspot models.
- `backend/app/models/event.py` — add latest snapshot/current core/spread/hot/rank/topic/time summary fields.
- `backend/app/api/__init__.py` — register hotspot blueprint.
- `backend/app/tasks/jobs.py` — implement `hotspot_job`.
- `backend/app/tasks/runner.py` — recover `hotspot` tasks.
- `backend/app/core/config.py` — hotspot, LDA, heat and LLM timeout settings.
- `backend/.env.example` — document hotspot settings.
- `backend/migrations/README.md` — document migration order.

---

### Task 1: Hotspot configuration and result types

**Files:**
- Create: `backend/app/analysis/hotspot_config.py`
- Create: `backend/app/analysis/topic_model.py`
- Test: `backend/tests/test_hotspot_algorithms.py`

- [ ] **Step 1: Write failing configuration and small-corpus tests.**

```python
def test_hotspot_config_hash_changes_with_heat_weight():
    assert HotspotConfig().config_hash() != HotspotConfig(core_weight=.8).config_hash()

def test_topic_candidates_follow_approved_ranges():
    assert candidate_topic_counts(10, 12) == [2, 3, 4]
    assert candidate_topic_counts(30, 12) == [3, 4, 5, 6, 7, 8]

def test_one_to_four_documents_use_keyword_fallback():
    result = discover_topics(_documents(3), _matrix(3), HotspotConfig())
    assert result.method == "keyword_topic_fallback"
    assert "KEYWORD_TOPIC_FALLBACK" in result.warnings
```

- [ ] **Step 2: Run the tests and verify import failure.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: collection fails because hotspot modules do not exist.

- [ ] **Step 3: Implement immutable configuration.**

`HotspotConfig` must expose approved defaults: 7-day window, max 12 topics, Top 20 words, random state 42, diversity `.70`, small-topic ratio `.20`, low-confidence `.45`, minimum 3 reports, 2 platforms, 24-hour recency/half-life, core/spread weights `.70/.30`, formula version `v1`. Validate positive ranges and require weights to sum to 1. Generate a stable SHA-256 hash from sorted JSON.

- [ ] **Step 4: Implement small-corpus topic result types.**

Define `TopicCandidateMetrics`, `DiscoveredTopic`, `ArticleTopicAssignment`, and `TopicDiscoveryResult`. For 1–4 documents, aggregate token frequency, create one topic with up to 20 terms, assign probability `1.0`, return `method="keyword_topic_fallback"`, and never call sklearn LDA.

- [ ] **Step 5: Run focused tests.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: configuration and small-corpus tests pass.

---

### Task 2: LDA candidate selection and deterministic assignments

**Files:**
- Modify: `backend/app/analysis/topic_model.py`
- Test: `backend/tests/test_hotspot_algorithms.py`

- [ ] **Step 1: Add failing tests for 5–9 fixed K, normal candidate selection, quality metrics, ties, probabilities, and reproducibility.**

Use synthetic count matrices with separable weather/entertainment vocabularies. Assert 5–9 documents train `K=2`; 10–29 evaluate `[2,3,4]`; selected topic keywords exist; every document has one primary assignment; probability vectors sum to approximately one; two runs with random state 42 return the same selected K and primary assignments.

- [ ] **Step 2: Run the tests and verify the new cases fail.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: missing LDA candidate implementation.

- [ ] **Step 3: Implement candidate generation and model metrics.**

Use `sklearn.decomposition.LatentDirichletAllocation(learning_method="batch", random_state=config.random_state)`. Compute perplexity, topic diversity from unique Top-20 terms, primary document counts, and the ratio of topics smaller than `max(2, ceil(N*.03))`.

- [ ] **Step 4: Implement selection rules.**

Filter candidates below diversity `.70` or above small-topic ratio `.20`; choose lowest perplexity; when perplexities differ by no more than 2%, choose smaller K. If all fail, choose lowest perplexity and emit `TOPIC_QUALITY_DEGRADED`. For each document persist the primary topic and probabilities at least `.05`, plus `LOW_TOPIC_CONFIDENCE` when the maximum is below `.45`.

- [ ] **Step 5: Run focused tests.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: all topic-model tests pass.

---

### Task 3: Topic naming and OpenAI-compatible DeepSeek client

**Files:**
- Modify: `backend/app/llm/client.py`
- Modify: `backend/app/analysis/topic_classifier.py`
- Test: `backend/tests/test_hotspot_algorithms.py`

- [ ] **Step 1: Write failing tests for valid JSON, enum validation, cache signatures, malformed output, HTTP failure, and deterministic keyword fallback.**

```python
def test_classify_topic_accepts_structured_llm_output():
    client = FakeClient('{"category":"自然灾害","topic_name":"重庆暴雨救援","confidence":0.9}')
    result = classify_topic(["重庆", "暴雨", "救援"], ["重庆暴雨持续"], client=client)
    assert result["method"] == "lda_llm"

def test_classify_topic_falls_back_on_invalid_json():
    result = classify_topic(["重庆", "暴雨", "救援"], [], client=FakeClient("bad"))
    assert result["category"] == "其他"
    assert result["method"] == "lda_keyword_fallback"
```

- [ ] **Step 2: Run focused tests and verify failure.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: current stub signature/result fails.

- [ ] **Step 3: Implement `LLMClient.chat`.**

POST to `<base_url>/chat/completions` with bearer authentication, configured model, JSON body, timeout and injectable `requests.Session`. Raise explicit `LLMUnavailableError` for missing key, non-2xx response, malformed response or missing content. Never log the API key.

- [ ] **Step 4: Implement structured topic naming.**

Accept keyword/title lists, render a prompt with the seven approved categories, parse optional Markdown-fenced JSON, validate enum/name/confidence, and return `lda_llm`. On any exception return category `其他`, name from the first 3–5 distinct keywords, confidence `0`, method `lda_keyword_fallback`, and warning `LLM_TOPIC_NAMING_DEGRADED`.

- [ ] **Step 5: Run focused tests.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: all naming/client tests pass without network access.

---

### Task 4: Hotspot persistence models and migration

**Files:**
- Create: `backend/app/models/hotspot.py`
- Modify: `backend/app/models/event.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/20260711_hotspot_discovery.sql`
- Create: `backend/migrations/migrate_hotspot_discovery.py`
- Modify: `backend/migrations/README.md`
- Test: `backend/tests/test_hotspot_migration.py`

- [ ] **Step 1: Write failing schema tests.**

Create an in-memory app and assert tables `hotspot_run`, `topic_result`, `topic_article_assignment`, `event_heat_snapshot`; unique `(analysis_run_id, config_hash, scope)`-compatible run indexes; unique `(hotspot_run_id, topic_index)` and `(hotspot_run_id, event_id)`; event current-summary columns; JSON columns and foreign keys. Test SQL splitting and MySQL-only runner guard.

- [ ] **Step 2: Run migration tests and verify failure.**

Run: `python -m pytest backend/tests/test_hotspot_migration.py -v`

Expected: models/tables are missing.

- [ ] **Step 3: Implement SQLAlchemy models.**

Use SQLite-compatible BIGINT variants. `HotspotRun` stores analysis/task/user/mode/scope, window, hashes/config/versions/metrics, topic/heat statuses, warnings/errors and timestamps. `TopicResult` stores topic index, keywords, naming fields, counts/mass/signature. `TopicArticleAssignment` stores article/content identity, probability and primary flag. `EventHeatSnapshot` stores raw/component JSON, core/spread/final heat, eligibility/rank/state/time confidence/formula/details.

- [ ] **Step 4: Add current event summary fields and migration.**

Add latest snapshot ID, current core/spread, hot flag/rank, topic category/name, first publish/last activity, independent report count, platform count and time confidence. The migration runner must inspect existing columns before applying `ALTER TABLE`, so rerunning is safe.

- [ ] **Step 5: Run migration and persistence tests.**

Run: `python -m pytest backend/tests/test_hotspot_migration.py backend/tests/test_persistence.py -v`

Expected: both suites pass.

---

### Task 5: Heat calculation, eligibility and ranking

**Files:**
- Create: `backend/app/analysis/heat_calculator.py`
- Modify: `backend/app/analysis/hot_detector.py`
- Test: `backend/tests/test_hotspot_algorithms.py`

- [ ] **Step 1: Write failing tests for time fallback, deduplicated reports, growth, platform percentiles, platform-local interactions, missing spread, 70/30 final heat, evidence gates and Top 20.**

Use fixed `calculated_at`. Assert duplicates do not increase independent reports; missing publish time uses first-crawled time and lowers confidence; raw engagement is log-transformed and normalized inside each platform; all-missing spread yields `final_heat == core_heat`; available spread yields `.7*core + .3*spread`; hotlist evidence can satisfy the two-platform alternative but never report count; inactive events fail eligibility.

- [ ] **Step 2: Run focused tests and verify failure.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: heat helpers are missing.

- [ ] **Step 3: Implement raw event statistics and normalization.**

Define typed `HeatArticle`, `EventHeatInput`, `EventHeatResult`. Calculate 7-day/24-hour/previous-24-hour counts, growth, platform set, latest activity, time confidence, article engagement from available metrics, duplicate/spam weights and 24-hour exponential decay. Convert event count/growth/platform/spread raw values to percentile scores; use 50 for a single-candidate percentile.

- [ ] **Step 4: Implement heat/ranking rules.**

Compute equal-weight core components, optional spread, final `.70/.30`, minimum 3 reports, 2 platforms or formal hotlist evidence, recent 24-hour activity, then rank eligible events and keep Top 20. Export compatibility functions from `hot_detector.py` without retaining the old clustering stub as hotspot logic.

- [ ] **Step 5: Run focused tests.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: all pure hotspot tests pass.

---

### Task 6: Hot-seed normalization contract

**Files:**
- Create: `backend/app/analysis/hot_seed.py`
- Test: `backend/tests/test_hotspot_algorithms.py`

- [ ] **Step 1: Write failing tests for topic-mark removal, whitespace/NFKC normalization, exact merge, cross-platform evidence, best rank and search-query output.**

Use `#重庆暴雨#`, `重庆多地暴雨` and duplicate platform snapshots. Assert normalized queries are deterministic, source snapshots remain traceable, and the result never exposes a report-count contribution.

- [ ] **Step 2: Run focused tests and verify failure.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: seed functions are missing.

- [ ] **Step 3: Implement seed dataclasses and merge rules.**

Define `HotSeedSnapshot` and `ExpansionSeed`. Normalize NFKC/space/topic markers/common platform suffixes, merge exact normalized titles, retain source IDs/platforms/ranks/snapshot times, compute a deterministic priority tuple, and return expansion queries. Do not perform external crawling in this pure module.

- [ ] **Step 4: Run focused tests.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py -v`

Expected: all seed tests pass.

---

### Task 7: Hotspot service, idempotence and heat persistence

**Files:**
- Create: `backend/app/services/hotspot_service.py`
- Modify: `backend/app/analysis/__init__.py`
- Test: `backend/tests/test_hotspot_service.py`

- [ ] **Step 1: Write failing service tests.**

Create successful `AnalysisRun` fixtures with representative/skipped articles and events. Test run creation only from successful analysis, dataset/config reuse, 7-day window metadata, topic persistence, complete primary assignment uniqueness, LLM fallback warnings, content-version mismatch rollback, no-event mapping behavior (`EVENT_AGGREGATION_PENDING`), heat snapshots when `Article.event_id` exists, event current-summary update, immutable prior snapshots and stale task lease rollback.

- [ ] **Step 2: Run service tests and verify failure.**

Run: `python -m pytest backend/tests/test_hotspot_service.py -v`

Expected: missing service/models.

- [ ] **Step 3: Implement `create_hotspot_run`.**

Validate mode/scope rules, require a successful analysis run, calculate window/hash/config fingerprints, reuse identical successful global/user runs, create pending `HotspotRun`, and link source task/user without copying full matrices.

- [ ] **Step 4: Implement `run_hotspot_analysis`.**

Verify all `content_identity` values, rebuild `AnalysisDocument` objects and Count matrix from frozen rows, run topic discovery, call topic naming once per topic, persist topic rows/assignments/metrics/warnings, then group representative articles with non-null `event_id`. If none exist, set `topic_status=success`, `heat_status=pending`, append `EVENT_AGGREGATION_PENDING`, and commit without inventing events.

- [ ] **Step 5: Implement heat persistence.**

For stable event mappings, load article/current snapshot data, calculate all event results together, insert one immutable snapshot per `(hotspot_run_id,event_id)`, set rank/state, update only the newest current event summary, and commit under the task lease. Re-running the same run must reuse rows rather than duplicate them.

- [ ] **Step 6: Run service tests.**

Run: `python -m pytest backend/tests/test_hotspot_service.py -v`

Expected: all service tests pass.

---

### Task 8: API, background job, recovery and serializers

**Files:**
- Create: `backend/app/api/hotspots.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/app/tasks/runner.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_hotspot_service.py`
- Test: `backend/tests/test_jobs.py`

- [ ] **Step 1: Add failing API/job tests.**

Test admin POST `/api/hotspots/runs` with `analysis_run_id`, owned/admin list/detail visibility, rejection of non-success analysis runs, synchronous background execution, task result/progress, recovery registry containing `hotspot`, and GET `/api/hotspots` returning real ranked snapshot data rather than `SAMPLE_EVENT`.

- [ ] **Step 2: Run focused tests and verify failure.**

Run: `python -m pytest backend/tests/test_hotspot_service.py backend/tests/test_jobs.py -v`

Expected: missing blueprint/job/recovery registration.

- [ ] **Step 3: Implement API and serializers.**

Create an admin-only run endpoint and authenticated list/detail/ranking endpoints. Return run IDs, task IDs, topic summaries, warnings, heat status, calculated time, formula version and coverage metadata; never expose full clean content in run detail.

- [ ] **Step 4: Implement `hotspot_job` and recovery.**

Read integer `hotspot_run_id`, update task stages, call `run_hotspot_analysis(task_id=...)`, write success/failure result, and add `hotspot` to default recovery registry. Reuse existing task lease/heartbeat semantics.

- [ ] **Step 5: Add configuration and env documentation.**

Expose all approved `HOTSPOT_*`, `LDA_*`, `HEAT_*` values and `LLM_REQUEST_TIMEOUT`; preserve existing defaults and clamp unsafe values.

- [ ] **Step 6: Run focused tests.**

Run: `python -m pytest backend/tests/test_hotspot_service.py backend/tests/test_jobs.py -v`

Expected: API and job suites pass.

---

### Task 9: Full regression, migration validation and documentation consistency

**Files:**
- Modify: `backend/migrations/README.md`
- Modify only if tests require: `backend/tests/test_contracts.py`

- [ ] **Step 1: Run hotspot suites.**

Run: `python -m pytest backend/tests/test_hotspot_algorithms.py backend/tests/test_hotspot_migration.py backend/tests/test_hotspot_service.py -v`

Expected: all hotspot tests pass.

- [ ] **Step 2: Run all backend tests.**

Run: `python -m pytest backend/tests -v`

Expected: all backend tests pass with zero failures.

- [ ] **Step 3: Run repository tests and syntax checks.**

Run: `python -m pytest -v`

Run: `python -m compileall backend/app backend/migrations`

Expected: all tests pass and compileall exits 0.

- [ ] **Step 4: Verify migration/model and design coverage.**

Run: `python -m pytest backend/tests/test_hotspot_migration.py backend/tests/test_contracts.py -v`

Expected: tables, columns, blueprint registration and public contracts pass.

- [ ] **Step 5: Inspect the final diff.**

Run: `git diff --check`

Run: `git status --short`

Expected: no whitespace errors; only intended hotspot files plus pre-existing user changes appear.

---

### Task 10: Hot-list seed expansion and automatic topic-analysis closure

**Files:**
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_jobs.py`

- [ ] Write a failing hot-crawl job test with a fake `_hot` source and ordinary search source.
- [ ] Verify the hot crawl currently stops after persisting the seed.
- [ ] Normalize the persisted hot-list titles, call ordinary search adapters with each expansion query, and persist returned documents.
- [ ] Create and run a `mode=hot` content-analysis snapshot for expanded reports, then create and run hotspot topic discovery in the same lease-safe background job.
- [ ] Return seed, expansion, analysis-run and hotspot-run counts/IDs in the crawl task result.
- [ ] Run `python -m pytest backend/tests/test_jobs.py -v` and verify the closure tests pass.

---

## Deliberate scope limits

- This plan does not implement Single-Pass event aggregation; it consumes stable `Article.event_id` mappings and reports `EVENT_AGGREGATION_PENDING` when none exist.
- The hot crawler expands only the configured Top-N seed queries with bounded per-seed targets; it does not recursively generate new seeds from expansion results.
- This plan does not implement sentiment, lifecycle prediction, risk assessment, event tracing or frontend charts.
