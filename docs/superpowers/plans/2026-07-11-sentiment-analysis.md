# Sentiment Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement versioned per-article hybrid sentiment analysis with LLM-first classification, SnowNLP fallback, duplicate inheritance, event daily trends, and current per-platform content-stance distributions.

**Architecture:** Pure sentiment parsing, fallback classification and aggregation live under `backend/app/analysis`. SQLAlchemy models persist immutable runs, article results and event/cluster snapshots, while the service layer owns frozen inputs, cache reuse, task leases, transactions and current Article/Event summaries. Existing hot and search jobs invoke sentiment only after event aggregation, preserving the global/search isolation rules.

**Tech Stack:** Python 3, Flask, Flask-SQLAlchemy, requests-based OpenAI-compatible LLM client, SnowNLP, SQLite tests, MySQL 8 migrations, unittest/pytest-compatible tests.

---

## File map

**Create**

- `backend/app/analysis/sentiment_config.py` — immutable versions, thresholds, limits and config hash.
- `backend/app/analysis/sentiment_aggregator.py` — article weights, overall counts/ratios, daily trend and platform breakdown.
- `backend/app/models/sentiment.py` — sentiment run, article result and event/cluster snapshot models.
- `backend/app/services/sentiment_analysis_service.py` — frozen input loading, reuse, execution, inheritance, persistence and queries.
- `backend/app/api/sentiment.py` — sentiment run and detailed result endpoints.
- `backend/migrations/20260711_sentiment_analysis.sql` — MySQL 8 schema and current-summary columns.
- `backend/migrations/migrate_sentiment_analysis.py` — idempotent MySQL migration runner.
- `backend/tests/test_sentiment_algorithms.py` — parsing, fallback, weighting, trend and platform tests.
- `backend/tests/test_sentiment_migration.py` — schema, constraints and migration tests.
- `backend/tests/test_sentiment_service.py` — run, persistence, reuse, inheritance, isolation and API tests.

**Modify**

- `backend/app/analysis/sentiment_analyzer.py` — replace the stub with LLM parsing and SnowNLP fallback.
- `backend/app/analysis/__init__.py` — export sentiment types and helpers.
- `backend/app/llm/prompts.py` — add the category-aware structured sentiment prompt.
- `backend/app/models/article.py` — add current article sentiment metadata and result pointer.
- `backend/app/models/event.py` — add current snapshot pointer, score and update time.
- `backend/app/models/__init__.py` — export sentiment models.
- `backend/app/core/config.py` and `backend/.env.example` — sentiment settings and versions.
- `backend/requirements.txt` — add a pinned SnowNLP dependency.
- `backend/app/services/event_service.py` — return real event sentiment snapshots and platform distributions.
- `backend/app/api/__init__.py`, `backend/app/api/events.py`, `backend/app/api/aggregation.py` — register sentiment APIs and cluster sentiment reads.
- `backend/app/tasks/jobs.py` — add `sentiment_job` and connect hot/search flows.
- `backend/app/tasks/runner.py` — include sentiment jobs in recovery.
- `backend/tests/test_jobs.py`, `backend/tests/test_contracts.py`, `backend/tests/test_event_aggregation_service.py` — pipeline and compatibility regressions.

**Worktree rule:** The current `main` worktree contains extensive user changes, including modified files this feature must extend. Do not create a clean worktree that omits those changes, and do not reset, checkout or clean. Do not make code commits that would mix pre-existing edits from shared files; only the already-isolated design/plan documents may be committed separately.

---

### Task 1: Sentiment configuration and structured LLM parsing

**Files:**
- Create: `backend/app/analysis/sentiment_config.py`
- Modify: `backend/app/analysis/sentiment_analyzer.py`
- Modify: `backend/app/llm/prompts.py`
- Modify: `backend/app/analysis/__init__.py`
- Test: `backend/tests/test_sentiment_algorithms.py`

- [ ] **Step 1: Write failing tests for stable config hashes and structured parsing.**

Create tests that assert default values include text limit `500`, neutral range `[-0.20, 0.20]`, platform sample thresholds `3/2`, algorithm version `sentiment-v1`, and Prompt version `sentiment-prompt-v1`. Two identical configs must share a SHA-256 hash; changing any result-affecting value must change it.

Add fake-client cases for valid JSON, fenced JSON, invalid label, score outside `[-1, 1]`, confidence outside `[0, 1]`, invalid dimension, and positive/negative label-score contradictions.

- [ ] **Step 2: Run the focused tests and verify the new modules are missing.**

Run: `python -m pytest tests/test_sentiment_algorithms.py -v`

Expected: collection/import failure for `sentiment_config` or missing analyzer interfaces.

- [ ] **Step 3: Implement the immutable configuration.**

Implement `SentimentConfig` with `as_dict()` and stable `config_hash()`. Validate thresholds, retry/concurrency counts, success ratio, text limit and platform minimums. Keep all result-affecting defaults in the dataclass so the service can reconstruct a run from persisted config.

- [ ] **Step 4: Implement typed article results and strict parsing.**

`analyze_sentiment(text, *, context=None, client=None, config=None)` must return a result containing:

```python
{
    "label": "positive" | "negative" | "neutral",
    "score": float,
    "confidence": float,
    "dimension": "stance" | "impact" | "factual",
    "target": str,
    "reason": str,
    "method": "llm",
    "model_name": str,
    "warnings": list[str],
}
```

Use `LLMClient.chat()` with a system message from `SENTIMENT_PROMPT` and a user message containing event category/name, event title, article title and cleaned text. Strip a single Markdown fence deterministically, parse JSON, validate enums/ranges and reject contradictory label-score combinations.

- [ ] **Step 5: Add the category-aware Prompt.**

The Prompt must explicitly distinguish `stance`, `impact` and `factual`; instruct disaster/accident handling; forbid sentiment decisions based only on casualty words; require concise target/reason fields; and require JSON only.

- [ ] **Step 6: Run the focused tests until parsing/config tests pass.**

Run: `python -m pytest tests/test_sentiment_algorithms.py -v`

Expected: all config and LLM parsing cases pass.

---

### Task 2: SnowNLP fallback and deterministic aggregation

**Files:**
- Create: `backend/app/analysis/sentiment_aggregator.py`
- Modify: `backend/app/analysis/sentiment_analyzer.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_sentiment_algorithms.py`

- [ ] **Step 1: Add failing tests for SnowNLP mapping and event aggregation.**

Use an injected probability function rather than the real model in unit tests. Assert `0.80 → positive/0.60`, `0.20 → negative/-0.60`, and `0.50 → neutral/0.0`; fallback confidence must not exceed the configured cap.

Add aggregation fixtures covering quality/spam weights, logarithmically bounded spread factors, duplicate factors, raw counts, weighted ratios summing to one, average score, publish-time daily buckets, observed-time fallback, platform grouping and `sample_insufficient`.

- [ ] **Step 2: Run the focused tests and confirm fallback/aggregation cases fail.**

Run: `python -m pytest tests/test_sentiment_algorithms.py -v`

- [ ] **Step 3: Implement SnowNLP fallback.**

Add `analyze_with_snownlp(text, *, probability_fn=None, config=None, context=None)`. Convert `p` with `score = 2*p - 1`, apply configured positive/negative thresholds, cap confidence, use `impact` only for known disaster/accident contexts, otherwise `factual`, and emit `SNOWNLP_FALLBACK`.

Pin `snownlp` in `requirements.txt`. Keep imports lazy so the application can report `SNOWNLP_UNAVAILABLE` instead of failing module import during startup.

- [ ] **Step 4: Implement aggregation types and functions.**

Create focused helpers:

```python
article_sentiment_weight(article, *, event_max_heat: float) -> tuple[float, dict]
summarize_sentiment(items, config) -> dict
build_daily_sentiment(items, config) -> list[dict]
build_platform_sentiment(items, config) -> list[dict]
```

Clamp quality/spam/duplicate inputs, bound spread factor to `[1, 2]`, preserve raw counts, normalize weighted ratios, and return explicit warnings for missing time and insufficient platform samples.

- [ ] **Step 5: Run the focused algorithm tests.**

Run: `python -m pytest tests/test_sentiment_algorithms.py -v`

Expected: LLM, SnowNLP, weighting, daily and platform tests pass.

---

### Task 3: Versioned schema and migrations

**Files:**
- Create: `backend/app/models/sentiment.py`
- Modify: `backend/app/models/article.py`
- Modify: `backend/app/models/event.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/20260711_sentiment_analysis.sql`
- Create: `backend/migrations/migrate_sentiment_analysis.py`
- Test: `backend/tests/test_sentiment_migration.py`

- [ ] **Step 1: Write failing schema tests.**

Assert `db.create_all()` creates `sentiment_run`, `article_sentiment_result` and `event_sentiment_snapshot`. Assert unique constraints for `(sentiment_run_id, article_id)` and the run fingerprint, foreign keys, indexes, version/evidence fields, current result/snapshot pointers, and idempotent model imports.

Verify the SQL file contains all tables, new Article/Event columns and indexes. Verify the runner rejects non-MySQL URLs before executing SQL.

- [ ] **Step 2: Run migration tests and confirm missing models/tables.**

Run: `python -m pytest tests/test_sentiment_migration.py -v`

- [ ] **Step 3: Implement SQLAlchemy models.**

Use `BigInteger().with_variant(Integer, "sqlite")` for run/result/snapshot IDs. Persist JSON config, versions, statistics, warnings, score details, daily trend and platform distribution. Add nullable `event_id` and `aggregation_cluster_id` to snapshots, with validation in the service that at least one target exists.

Add Article current metadata (`sentiment_confidence`, `sentiment_dimension`, `sentiment_target`, `sentiment_content_identity`, `current_sentiment_result_id`, `sentiment_analyzed_at`) and Event current metadata (`current_sentiment_snapshot_id`, `sentiment_score`, `sentiment_updated_at`) without removing existing fields.

- [ ] **Step 4: Implement the MySQL migration.**

Follow the event aggregation migration pattern: validate a MySQL URL, read a UTF-8 SQL file, split and execute statements idempotently, and never delete/reset existing data. Use conditional information-schema checks before adding columns or indexes that may already exist.

- [ ] **Step 5: Run migration tests.**

Run: `python -m pytest tests/test_sentiment_migration.py -v`

Expected: all schema and migration contract tests pass.

---

### Task 4: Sentiment run lifecycle and frozen inputs

**Files:**
- Create: `backend/app/services/sentiment_analysis_service.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_sentiment_service.py`

- [ ] **Step 1: Add failing tests for run creation, scope and frozen datasets.**

Create global and search aggregation fixtures. Assert only successful aggregation runs are accepted, mode/scope are inherited, the dataset hash includes cluster/event membership plus content identities, identical successful/running runs are reused, and failed runs create a new attempt.

Assert a changed `content_identity` raises `DATASET_CHANGED` before any current summary field is updated.

- [ ] **Step 2: Run the focused tests and verify service imports fail.**

Run: `python -m pytest tests/test_sentiment_service.py -v`

- [ ] **Step 3: Implement configuration loading and run creation.**

Map all `SENTIMENT_*` and `SNOWNLP_*` environment settings to `SentimentConfig`. Create `create_sentiment_run(aggregation_run_id, source_task_id=None, user_id=None, config=None)` with a process lock plus database uniqueness handling matching existing analysis/aggregation services.

- [ ] **Step 4: Implement frozen member loading.**

For `global`, load current active `EventArticleMembership` members for each resolved event touched by the aggregation run. For `search_shared/manual`, load `AggregationAssignment` rows grouped by cluster. Exclude invalid/advertisement/zero-NLP-weight/hotlist-only articles, verify content identities, resolve representatives and duplicates, and compute a stable dataset hash.

- [ ] **Step 5: Run lifecycle tests.**

Run: `python -m pytest tests/test_sentiment_service.py -v`

Expected: creation, reuse, scope and dataset-change tests pass.

---

### Task 5: Article analysis, cache reuse and duplicate inheritance

**Files:**
- Modify: `backend/app/services/sentiment_analysis_service.py`
- Test: `backend/tests/test_sentiment_service.py`

- [ ] **Step 1: Add failing execution tests.**

Use injected fake LLM and fallback functions. Cover LLM success, invalid output → SnowNLP, missing API key → SnowNLP, both methods failing, compatible historical result reuse, Prompt/model version cache miss, and duplicate inheritance without additional LLM calls.

Assert detailed statistics distinguish `llm_count`, `snownlp_count`, `reused_count`, `inherited_count`, `failed_count` and `skipped_count`.

- [ ] **Step 2: Run focused tests and confirm execution is absent.**

Run: `python -m pytest tests/test_sentiment_service.py -v`

- [ ] **Step 3: Implement representative analysis and reuse.**

Before calling the LLM, query a compatible successful `ArticleSentimentResult` by article/content/config/model/Prompt/preprocess versions. Copy the normalized result into the current run with `method` preserved and a reuse warning. For cache misses, call LLM with bounded retry rules, then SnowNLP fallback.

- [ ] **Step 4: Implement duplicate inheritance.**

Analyze representatives first, then create a result for each duplicate with `method="inherited"`, `inherited_from_result_id`, identical semantic fields and duplicate-specific weight details. Missing representative results generate `DUPLICATE_SENTIMENT_SOURCE_MISSING` and do not trigger a separate LLM call.

- [ ] **Step 5: Enforce the minimum success ratio and atomic commit.**

If successful/reused/inherited results divided by analyzable inputs is below the configured ratio, mark the run failed and retain old current summaries. Otherwise persist results, revalidate task lease and content identities, and continue to snapshot generation in the same final transaction.

- [ ] **Step 6: Run execution tests.**

Run: `python -m pytest tests/test_sentiment_service.py -v`

Expected: reuse, fallback, inheritance and failure-ratio tests pass.

---

### Task 6: Event/cluster snapshots and current summaries

**Files:**
- Modify: `backend/app/services/sentiment_analysis_service.py`
- Modify: `backend/app/services/event_service.py`
- Test: `backend/tests/test_sentiment_service.py`

- [ ] **Step 1: Add failing snapshot tests.**

Assert a global run writes one immutable snapshot per formal event, updates Event current ratios/score/pointer, and updates each Article current result summary. Assert a search run writes cluster snapshots but leaves all formal Event rows unchanged.

Verify raw counts, weighted ratios, daily trend, time-source warnings, platform distributions and insufficient-sample flags. Verify rerunning the same successful run creates no duplicate snapshots.

- [ ] **Step 2: Run focused tests and confirm snapshot behavior fails.**

Run: `python -m pytest tests/test_sentiment_service.py -v`

- [ ] **Step 3: Implement snapshot persistence.**

Group current run results by formal event or aggregation cluster, call the pure aggregator, persist immutable JSON summaries, and update Article current fields only when the current result matches the article's current content identity. Update Event current fields only for `scope=global`.

- [ ] **Step 4: Replace placeholder event sentiment serialization.**

`get_event_detail()` and `/api/events/{id}/sentiment` must read `current_sentiment_snapshot_id`, with a fallback to existing Event ratios for pre-migration data. Return `raw_counts`, `weighted_ratios`, `average_score`, `daily_trend`, `platform_distribution`, calculation time, versions and warnings.

- [ ] **Step 5: Run snapshot/service tests.**

Run: `python -m pytest tests/test_sentiment_service.py -v`

Expected: global/search isolation and serialization tests pass.

---

### Task 7: APIs, permissions and background task integration

**Files:**
- Create: `backend/app/api/sentiment.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/api/events.py`
- Modify: `backend/app/api/aggregation.py`
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/app/tasks/runner.py`
- Test: `backend/tests/test_sentiment_service.py`
- Test: `backend/tests/test_jobs.py`

- [ ] **Step 1: Add failing API and job tests.**

Cover administrator run creation, run detail, paginated article results, ordinary-user formal event reads, shared search cluster reads, private manual-run denial, detailed reason/raw-response admin restriction, and invalid IDs/pagination.

Add job tests asserting:

```text
hot: aggregation → heat → sentiment
search: aggregation → sentiment
standalone sentiment task → result stored on task
recovery registry includes sentiment
```

All tests inject fake sentiment analyzers and must not call a real LLM or SnowNLP model.

- [ ] **Step 2: Run API/job tests and confirm endpoints/jobs are missing.**

Run: `python -m pytest tests/test_sentiment_service.py tests/test_jobs.py -v`

- [ ] **Step 3: Implement sentiment API endpoints.**

Register `/api/sentiment`. Make run creation admin-only, run lists/details owner-or-admin according to scope, detailed article results admin-only, and summary reads available for formal events and shared search clusters.

- [ ] **Step 4: Implement `sentiment_job`.**

Validate `sentiment_run_id`, update progress, call `run_sentiment_analysis`, respect task leases and store the result. Add it to the recovery registry without changing existing job semantics.

- [ ] **Step 5: Connect existing pipelines.**

After global heat finalization, create/run sentiment and expose `sentiment_run_id` in the hot task result. After search aggregation, create/run search sentiment and expose `sentiment_run_id` and cluster summaries. Reused successful sentiment runs must not call the analyzer again.

- [ ] **Step 6: Run API/job tests.**

Run: `python -m pytest tests/test_sentiment_service.py tests/test_jobs.py -v`

Expected: permission, endpoint, pipeline and recovery tests pass.

---

### Task 8: Compatibility, contracts and documentation alignment

**Files:**
- Modify: `backend/tests/test_contracts.py`
- Modify: `backend/tests/test_event_aggregation_service.py`
- Modify: `README.md`
- Modify: `docs/framework_overview.md`

- [ ] **Step 1: Add failing compatibility contracts.**

Assert Config exposes all sentiment settings, blueprints register expected routes, event responses retain existing `positive/negative/neutral` compatibility keys, aggregation results remain unchanged when sentiment is absent, and new current-summary fields are nullable for old rows.

- [ ] **Step 2: Run compatibility tests.**

Run: `python -m pytest tests/test_contracts.py tests/test_event_aggregation_service.py -v`

- [ ] **Step 3: Make minimal compatibility fixes.**

Keep existing response fields while adding richer snapshot objects. Do not change event aggregation thresholds, membership behavior, search cache fingerprinting or hotspot heat semantics.

- [ ] **Step 4: Update current project documentation.**

Document the new pipeline stage, SnowNLP dependency, configuration, migration command and enhanced event sentiment response. Do not rewrite historical module designs or unrelated README sections.

- [ ] **Step 5: Run compatibility tests again.**

Run: `python -m pytest tests/test_contracts.py tests/test_event_aggregation_service.py -v`

Expected: existing and new contracts pass.

---

### Task 9: Final verification

**Files:**
- Review all files touched above.

- [ ] **Step 1: Run sentiment-focused tests.**

Run:

```powershell
cd backend
python -m pytest tests/test_sentiment_algorithms.py tests/test_sentiment_migration.py tests/test_sentiment_service.py -q
```

Expected: all sentiment tests pass without network calls.

- [ ] **Step 2: Run related pipeline regressions.**

Run:

```powershell
python -m pytest tests/test_jobs.py tests/test_event_aggregation_service.py tests/test_hotspot_service.py tests/test_contracts.py -q
```

Expected: all related tests pass.

- [ ] **Step 3: Run the complete backend suite.**

Run: `python -m pytest -q`

Expected: zero failures.

- [ ] **Step 4: Run compilation and whitespace checks.**

Run from the project root:

```powershell
python -m compileall -q backend/app backend/migrations
git diff --check
```

Expected: both commands exit `0`; line-ending warnings may be reported by Git but whitespace errors must be absent.

- [ ] **Step 5: Inspect the final worktree without altering unrelated changes.**

Run: `git status --short --branch`

Confirm only intended sentiment files plus the user's pre-existing changes are present. Do not reset, checkout, clean or create a mixed code commit.

---

## 当前实施与待验证状态（2026-07-11）

用户要求暂时停止测试。以下状态只记录已经实际执行过的结果，不把未运行项目表述为通过。

### 已执行过的局部验证

- `tests/test_sentiment_algorithms.py`：曾执行，最近一次结果为 `9 passed`。
- `tests/test_sentiment_migration.py`：曾执行，最近一次结果为 `4 passed`。
- 情感服务的运行复用、搜索隔离、正式事件摘要、重复文章继承、SnowNLP 降级、内容版本变化回滚、事件/搜索簇接口、后台情感任务等测试曾分别执行并通过。
- 热点采集闭环增加 `sentiment_run_id` 后，对应单项任务测试曾执行并通过。
- 情感配置契约单项测试曾执行并通过。

这些是修改过程中的局部结果。后续代码发生过继续修改，因此不能替代最终专项或完整回归测试。

### 已发现但尚未完成验证的行为

- `test_transient_llm_failure_retries_before_fallback` 最近一次执行失败。
- 当前服务在第一次 LLM 异常后直接进入 SnowNLP 降级，尚未完成“临时错误最多重试 3 次，再降级”的实现与验证。
- 401/403、配置缺失等不可重试错误与 429/5xx、超时等可重试错误尚未完成分类验证。
- `SENTIMENT_LLM_MAX_CONCURRENCY` 已进入设计与配置，但有限并发执行尚未实现和验证；当前服务按确定性顺序逐篇处理。

### 尚未执行的情感专项测试

- 未在当前最终代码状态下整体运行：

```powershell
python -m pytest tests/test_sentiment_algorithms.py tests/test_sentiment_migration.py tests/test_sentiment_service.py -q
```

- 尚未完整验证同一次运行中单篇 LLM 与 SnowNLP 均失败、但整体成功比例仍达到门槛时继续完成其他文章。
- 尚未完整验证低于 `SENTIMENT_MIN_SUCCESS_RATIO` 时回滚文章当前摘要、事件当前摘要和快照。
- 尚未完整验证跨运行缓存对算法版本、模型版本、Prompt 版本和预处理版本的全部隔离组合。
- 尚未完整验证多个事件、多个搜索事件簇在同一次情感运行中的快照唯一性。
- 尚未完整验证重复文章找不到代表文章结果时的跳过与警告。
- 尚未完整验证任务租约失效时禁止提交情感结果。
- 尚未完整验证并发创建相同情感运行时的数据库唯一约束竞争。

### 尚未执行的 API 与权限测试

- `POST /api/sentiment/runs` 管理员创建、成功结果复用和运行中任务复用。
- 普通用户禁止创建情感运行。
- 普通用户只能读取自己的私有手动运行。
- 全用户可以读取共享搜索事件簇汇总，但不能读取其他用户的搜索历史。
- `GET /api/sentiment/runs/{id}/results` 仅管理员可读取详细理由。
- 非法分页、无效运行 ID、无效事件 ID 和无效事件簇 ID。
- 原始 LLM 响应不向普通用户返回。

### 尚未执行的任务链与相关模块回归

- 未整体运行：

```powershell
python -m pytest tests/test_jobs.py tests/test_event_aggregation_service.py tests/test_hotspot_service.py tests/test_contracts.py -q
```

- 尚未验证普通关键词搜索完整链路：采集 → 预处理 → 内容分析 → 搜索事件聚合 → 情感分析。
- 尚未验证独立热点任务：主题发现 → 事件聚合 → 热度快照 → 情感分析。
- 尚未验证情感任务加入后台恢复注册表后的恢复行为。
- 尚未验证情感模块不会改变事件成员、热度快照、搜索缓存和正式事件发布语义。
- 尚未验证报告服务读取新版情感快照后的兼容性。

### 尚未执行的完整与静态验证

- 未运行完整后端测试：`python -m pytest -q`。
- 未运行最终编译检查：`python -m compileall -q backend/app backend/migrations`。
- 未运行最终差异检查：`git diff --check`。
- 未检查最终测试收集数量。
- 未在 MySQL 8 实例上实际执行 `migrate_sentiment_analysis.py`。
- 未使用真实 DeepSeek API 进行少量人工联调。
- 未人工检查 SnowNLP 对灾害、事故、否定、反讽和新闻客观语体的实际降级效果。
- 未进行前端饼图、每日趋势和分平台内容立场的联调展示。

在恢复测试前，不应宣称情感模块整体完成、全部测试通过或完整闭环已经验证。
