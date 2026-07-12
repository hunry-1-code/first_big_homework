# Event Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement reproducible event aggregation, stable global event membership, shared 24-hour search aggregation cache, and historical/similar event retrieval, then connect hotspot topic discovery to heat calculation through stable event mappings.

**Architecture:** Pure scoring and deterministic Single-Pass clustering live under `backend/app/analysis`. SQLAlchemy models persist aggregation runs, run-scoped clusters, assignment evidence, active membership history, versioned event representations, and merge candidates. Services own snapshots, idempotence, transactions, search cache, publication and read-only historical retrieval; background jobs orchestrate content analysis → hotspot topics → aggregation → heat.

**Tech Stack:** Python 3, Flask, Flask-SQLAlchemy, NumPy/scipy/scikit-learn, SQLite tests, MySQL 8 migrations, unittest/pytest-compatible tests.

---

## File map

**Create**

- `backend/app/analysis/aggregation_config.py` — immutable thresholds, weights, version and config hash.
- `backend/app/analysis/event_similarity.py` — cosine/Jaccard/time scoring, weight renormalization and hard-conflict decisions.
- `backend/app/analysis/event_candidate_retriever.py` — deterministic topic/keyword/entity/time candidate ordering.
- `backend/app/analysis/event_clusterer.py` — typed documents/clusters, Single-Pass actions and run-local merge pass.
- `backend/app/models/event_aggregation.py` — aggregation persistence models.
- `backend/app/services/event_aggregation_service.py` — run creation, frozen input loading, global/search persistence and cache lookup.
- `backend/app/services/event_similarity_service.py` — historical search and related-event Top 5.
- `backend/app/api/aggregation.py` — run, cluster, assignment, publish and merge-candidate endpoints.
- `backend/migrations/20260711_event_aggregation.sql` — MySQL 8 tables and indexes.
- `backend/migrations/migrate_event_aggregation.py` — idempotent MySQL runner.
- `backend/tests/test_event_aggregation_algorithms.py` — pure algorithm tests.
- `backend/tests/test_event_aggregation_migration.py` — schema and SQL tests.
- `backend/tests/test_event_aggregation_service.py` — run/persistence/cache/publish tests.
- `backend/tests/test_event_similarity_service.py` — historical and related-event tests.

**Modify**

- `backend/app/models/__init__.py` — export aggregation models.
- `backend/app/core/config.py` and `backend/.env.example` — aggregation thresholds, versions and cache TTL.
- `backend/app/services/hotspot_service.py` — expose topic-only and heat-finalization stages while retaining compatibility.
- `backend/app/services/event_service.py` — serialize related-event search results.
- `backend/app/api/__init__.py` and `backend/app/api/events.py` — register aggregation API and similar-event endpoint.
- `backend/app/tasks/jobs.py` — aggregation job plus hot pipeline orchestration.
- `backend/app/tasks/runner.py` — recover aggregation tasks.
- `backend/app/api/hotspots.py` — create the complete hotspot pipeline task.
- `backend/app/analysis/hot_detector.py` — delegate compatibility assignment to the new clusterer.
- `backend/tests/test_hotspot_service.py`, `backend/tests/test_jobs.py`, `backend/tests/test_contracts.py` — regression and end-to-end coverage.

---

### Task 1: Aggregation configuration and pure scoring

**Files:**
- Create: `backend/app/analysis/aggregation_config.py`
- Create: `backend/app/analysis/event_similarity.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_event_aggregation_algorithms.py`

- [ ] **Step 1: Write failing tests for stable config hashes, normalized cosine, missing-signal weight renormalization, thresholds and hard conflicts.**

Tests must construct an `AggregationConfig`, assert default `attach_threshold == 0.72`, `create_threshold == 0.58`, `move_margin == 0.15`, and verify two identical configs share a hash while a threshold change alters it. Add scoring cases where BGE is missing and remaining weights sum to one, and where conflicting non-empty locations force `hard_conflict=True`.

- [ ] **Step 2: Run the focused tests and verify imports fail.**

Run: `python -m pytest backend/tests/test_event_aggregation_algorithms.py -v`

Expected: collection fails because aggregation modules do not exist.

- [ ] **Step 3: Implement immutable config and scoring result types.**

`AggregationConfig` must validate `create_threshold < attach_threshold`, non-negative weights, and expose `as_dict()` plus SHA-256 `config_hash()`. `score_event_match()` accepts optional BGE/TF-IDF/entity/time scores, renormalizes only available weights, clamps values to `[0, 1]`, and returns component scores, normalized weights, final score, hard-conflict flag and structured reasons.

- [ ] **Step 4: Add environment-backed defaults.**

Add `EVENT_AGGREGATION_ATTACH_THRESHOLD=0.72`, `CREATE_THRESHOLD=0.58`, `MOVE_MARGIN=0.15`, BGE/TF-IDF/entity/time weights, algorithm version, candidate limit, search cache hours `24`, related-event limit `5`, and minimum evidence count.

- [ ] **Step 5: Run the focused tests until green.**

Run: `python -m pytest backend/tests/test_event_aggregation_algorithms.py -v`

Expected: scoring/config tests pass.

---

### Task 2: Candidate retrieval and deterministic Single-Pass clustering

**Files:**
- Create: `backend/app/analysis/event_candidate_retriever.py`
- Create: `backend/app/analysis/event_clusterer.py`
- Modify: `backend/app/analysis/hot_detector.py`
- Test: `backend/tests/test_event_aggregation_algorithms.py`

- [ ] **Step 1: Add failing tests for deterministic ordering, same-event attachment, different-location separation, low evidence deferral, center normalization and run-local merge.**

Use typed documents with IDs, publish times, TF-IDF/BGE vectors, keyword/entity sets and topic metadata. Assert input is sorted by effective time then ID; similar cross-platform articles attach; identical semantic vectors with conflicting locations create separate clusters; documents with no valid signal defer; repeated runs return identical assignments.

- [ ] **Step 2: Run tests and confirm the clusterer is missing.**

Run: `python -m pytest backend/tests/test_event_aggregation_algorithms.py -v`

- [ ] **Step 3: Implement candidate ordering and typed cluster state.**

Candidate retrieval must prefer compatible topic category, keyword/entity overlap and time range, then sort deterministically by descending evidence and stable candidate ID. It must not use run-local LDA topic index as a global identity.

- [ ] **Step 4: Implement Single-Pass and post-merge.**

For each representative document, score candidate clusters, attach at `>=0.72`, create below `0.58`, and conservatively create in the gray zone unless secondary evidence reaches the attach rule. Recompute mean TF-IDF and normalized mean BGE centers from members. Post-merge only run-local clusters with no hard conflict; never merge two formal event IDs automatically.

- [ ] **Step 5: Preserve compatibility.**

Update `assign_event_cluster()` to call the new scoring/selection logic for dictionary inputs while preserving the legacy return keys `event_id`, `action`, `similarity`, and `threshold`.

- [ ] **Step 6: Run algorithm tests.**

Run: `python -m pytest backend/tests/test_event_aggregation_algorithms.py -v`

Expected: all algorithm tests pass.

---

### Task 3: Aggregation schema and migration

**Files:**
- Create: `backend/app/models/event_aggregation.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/20260711_event_aggregation.sql`
- Create: `backend/migrations/migrate_event_aggregation.py`
- Test: `backend/tests/test_event_aggregation_migration.py`

- [ ] **Step 1: Write failing schema tests.**

Assert tables `aggregation_run`, `aggregation_cluster`, `aggregation_assignment`, `event_article_membership`, `event_representation`, and `event_merge_record`; required foreign keys; unique run fingerprint with attempt; unique `(aggregation_run_id, article_id)` and `(aggregation_run_id, cluster_index)`; unique nullable `active_article_id`; representation version uniqueness; JSON/status fields and indexes.

- [ ] **Step 2: Run migration tests and verify failure.**

Run: `python -m pytest backend/tests/test_event_aggregation_migration.py -v`

- [ ] **Step 3: Implement SQLite-compatible SQLAlchemy models.**

Use `BigInteger().with_variant(Integer, "sqlite")` for autoincrement keys. Store score details and reasons as JSON. `EventArticleMembership.active_article_id` is nullable and unique; active rows set it to `article_id`, inactive historical rows set it to `NULL`.

- [ ] **Step 4: Implement MySQL SQL and idempotent runner.**

The runner must reject non-MySQL URLs, split comments/statements consistently with existing migration runners, and rely on `CREATE TABLE IF NOT EXISTS`. SQL must use InnoDB, utf8mb4, named constraints and indexes.

- [ ] **Step 5: Run migration tests.**

Run: `python -m pytest backend/tests/test_event_aggregation_migration.py -v`

Expected: all schema tests pass.

---

### Task 4: Aggregation run creation and frozen input loading

**Files:**
- Create: `backend/app/services/event_aggregation_service.py`
- Test: `backend/tests/test_event_aggregation_service.py`

- [ ] **Step 1: Write failing service tests for run validation and reuse.**

Create in-memory articles, `DocumentFeatures`, a successful `AnalysisRun`, `AnalysisRunArticle` rows, optional `HotspotRun` and topic assignments. Test: only successful analysis runs are accepted; hotspot run must belong to the analysis run; identical config/data reuses a non-failed run; failed run creates the next attempt; scope derives from mode unless explicitly publishing.

- [ ] **Step 2: Run service tests and confirm missing service.**

Run: `python -m pytest backend/tests/test_event_aggregation_service.py -v`

- [ ] **Step 3: Implement `create_aggregation_run()`.**

Build versions/config hashes from Flask config, copy dataset/query fingerprints, set search cache expiry only after success, use an `RLock` plus unique fingerprint to handle races, and never copy full sparse matrices into JSON.

- [ ] **Step 4: Implement `_load_frozen_documents()`.**

Verify every `content_identity`, load representative rows and duplicates, rebuild the current run TF-IDF matrix with the analysis run's `FeatureConfig`, load compatible `ArticleEmbedding` rows, and map primary topic assignments when available. Missing BGE is a warning, not a fatal error.

- [ ] **Step 5: Run service tests.**

Run: `python -m pytest backend/tests/test_event_aggregation_service.py -v`

Expected: run creation, reuse, attempt and snapshot tests pass.

---

### Task 5: Persist search clusters and formal event membership

**Files:**
- Modify: `backend/app/services/event_aggregation_service.py`
- Test: `backend/tests/test_event_aggregation_service.py`

- [ ] **Step 1: Add failing search-scope tests.**

Run aggregation with `scope=search_shared`; assert clusters and assignments persist, `resolved_event_id` remains null, no `Event` is created, and no `Article.event_id` changes. Re-running the same successful run must not duplicate rows.

- [ ] **Step 2: Add failing global-scope tests.**

Assert a new cluster creates one formal `Event`, active memberships and article pointers; a later run attaches related articles to the same stable event; duplicate-group non-representatives inherit the representative event but do not increase representation member count; changed datasets roll back without partial rows.

- [ ] **Step 3: Implement `run_event_aggregation()`.**

Set running timestamps, load frozen inputs, call the pure clusterer, persist run-scoped clusters/assignments, then for global scope resolve clusters against formal event candidates, create/attach/unchanged/moved/deferred actions and commit atomically after `assert_task_lease()`.

- [ ] **Step 4: Implement membership history.**

On attach/create set one active membership and `Article.event_id`. On move close the old membership (`active_article_id=NULL`, `valid_to=now`) before inserting the new active row. Require the configured 0.15 score margin and no hard conflict. Compute event title/time/report/platform summaries from active members.

- [ ] **Step 5: Implement representation recomputation.**

For active representative members with compatible cached BGE, calculate the normalized mean and upsert `EventRepresentation` by event/model/version/preprocess. Aggregate keywords/entities deterministically. Do not store run TF-IDF in the representation table.

- [ ] **Step 6: Run service tests.**

Run: `python -m pytest backend/tests/test_event_aggregation_service.py -v`

Expected: search isolation, global stability, history and rollback tests pass.

---

### Task 6: Shared 24-hour search cache and controlled publication

**Files:**
- Modify: `backend/app/services/event_aggregation_service.py`
- Test: `backend/tests/test_event_aggregation_service.py`

- [ ] **Step 1: Write failing cache-boundary tests.**

Test 23:59:59 is fresh, exactly 24:00:00 is stale, stale lookup returns the most recent successful run, config/model changes invalidate reuse, and concurrent equivalent refresh requests return one existing pending/running run.

- [ ] **Step 2: Implement normalized search fingerprints and cache lookup.**

Normalize query with NFKC, collapsed whitespace and topic-marker removal; sort platforms; include mode/language/range. Return `{run, cached, stale, refresh_required}` without storing user identity in shared cache rows.

- [ ] **Step 3: Write failing publication tests.**

Only admin-facing service calls may publish. Publishing freezes a successful search cluster, creates a `mode=publish, scope=global` run, re-matches formal events, and records the resulting `resolved_event_id`. Repeated publication returns the same successful global result.

- [ ] **Step 4: Implement `publish_cluster()` and merge candidates.**

Do not copy local rank/heat. Use the search cluster members as frozen global input, create or attach a formal event, and create `EventMergeRecord(status="pending")` when two existing formal event candidates are strongly related. Confirmation closes source memberships and redirects them to target in one transaction; rejection only updates review metadata.

- [ ] **Step 5: Run cache/publication tests.**

Run: `python -m pytest backend/tests/test_event_aggregation_service.py -v`

Expected: cache and publication tests pass.

---

### Task 7: Historical search and related-event retrieval

**Files:**
- Create: `backend/app/services/event_similarity_service.py`
- Modify: `backend/app/services/event_service.py`
- Modify: `backend/app/api/events.py`
- Test: `backend/tests/test_event_similarity_service.py`

- [ ] **Step 1: Write failing tests for `same_event` versus `related_event`.**

Create formal events with compatible versioned representations. Assert historical search uses title/topic/keyword matching then semantic reorder; related-event lookup excludes self and merged aliases; different-location but semantically similar events are returned as related without changing membership; default limit is five; BGE absence falls back to keywords/entities/topic.

- [ ] **Step 2: Run focused tests and confirm missing service.**

Run: `python -m pytest backend/tests/test_event_similarity_service.py -v`

- [ ] **Step 3: Implement read-only related scoring.**

Use BGE 0.65, keyword 0.15, entity 0.15 and topic 0.05, renormalizing available signals. Do not use event time as a semantic penalty, but support optional before/after filters. Return match reasons and representation version.

- [ ] **Step 4: Upgrade event search and add endpoint.**

Keep SQL `LIKE` as fallback, add semantic reorder when an event/query representation is available, and add `GET /api/events/<id>/similar?limit=5`. Validate `limit` in `1..20`. The service must perform no writes or commits.

- [ ] **Step 5: Run similarity and event API tests.**

Run: `python -m pytest backend/tests/test_event_similarity_service.py backend/tests/test_hotspot_service.py -v`

Expected: retrieval tests and existing event endpoints pass.

---

### Task 8: Aggregation API and background task recovery

**Files:**
- Create: `backend/app/api/aggregation.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/app/tasks/runner.py`
- Test: `backend/tests/test_event_aggregation_service.py`
- Test: `backend/tests/test_jobs.py`

- [ ] **Step 1: Write failing API tests.**

Admin can create a run from an analysis run, list/detail runs, page clusters/assignments, publish a cluster and confirm/reject merge candidates. Normal users may read authorized search results but cannot publish or review merges. Invalid IDs/scopes/pages return 400/404 without creating tasks.

- [ ] **Step 2: Implement serialization and API routes.**

Register `/api/aggregation`; use existing `ok/fail`, `login_required/admin_required`, task creation and runner patterns. Detailed scores are admin-only. Reused successful runs return no task; reused pending runs return their task ID.

- [ ] **Step 3: Add `aggregation_job()`.**

Load integer `aggregation_run_id`, update progress through validation/clustering/persistence, call `run_event_aggregation()`, and finish with sanitized statistics. Register task type `aggregation` in recovery.

- [ ] **Step 4: Run API/job tests.**

Run: `python -m pytest backend/tests/test_event_aggregation_service.py backend/tests/test_jobs.py -v`

Expected: aggregation API, job and recovery tests pass.

---

### Task 9: Connect hotspot topic discovery → aggregation → heat

**Files:**
- Modify: `backend/app/services/hotspot_service.py`
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/app/api/hotspots.py`
- Test: `backend/tests/test_hotspot_service.py`
- Test: `backend/tests/test_jobs.py`

- [ ] **Step 1: Write failing end-to-end hotspot tests.**

Start with articles lacking `event_id`. After the complete hotspot task, assert topic discovery succeeds, an aggregation run exists, articles map to formal events, heat snapshots exist, `heat_status=success`, and public hotspots return those events. BGE failure must still complete through fallback. Existing direct topic-only behavior must continue returning `EVENT_AGGREGATION_PENDING` when deliberately invoked without orchestration.

- [ ] **Step 2: Split hotspot internal stages.**

Expose `discover_hotspot_topics()` and `finalize_hotspot_heat()` using existing `_load_documents`, `_persist_topics` and `_persist_heat`. Preserve `run_hotspot_analysis()` as a compatibility wrapper so current API/tests are not silently broken.

- [ ] **Step 3: Orchestrate the full hot pipeline.**

After content analysis, discover topics, create/run global aggregation, then finalize heat using stable mappings. Store `aggregation_run_id` in task results and progress messages. A repeated pipeline must reuse successful analysis/hotspot/aggregation artifacts without duplicating heat snapshots.

- [ ] **Step 4: Run hotspot and job tests.**

Run: `python -m pytest backend/tests/test_hotspot_service.py backend/tests/test_jobs.py -v`

Expected: legacy and full-loop tests pass.

---

### Task 10: Contract, migration and full regression verification

**Files:**
- Modify: `backend/tests/test_contracts.py`
- Modify: `README.md` only if public endpoints/task types documented there already.

- [ ] **Step 1: Add contract assertions.**

Assert aggregation task payload/result shape, model exports, blueprint registration, API authorization, non-leaking task results, default config values and stable public event response fields.

- [ ] **Step 2: Run all aggregation-focused tests.**

Run:

```powershell
python -m pytest backend/tests/test_event_aggregation_algorithms.py backend/tests/test_event_aggregation_migration.py backend/tests/test_event_aggregation_service.py backend/tests/test_event_similarity_service.py -v
```

Expected: all pass.

- [ ] **Step 3: Run related regression tests.**

Run:

```powershell
python -m pytest backend/tests/test_content_analysis_features.py backend/tests/test_content_analysis_service.py backend/tests/test_hotspot_algorithms.py backend/tests/test_hotspot_migration.py backend/tests/test_hotspot_service.py backend/tests/test_jobs.py backend/tests/test_contracts.py -v
```

Expected: all pass.

- [ ] **Step 4: Run the complete backend test suite.**

Run: `python -m pytest backend/tests -q`

Expected: zero failures.

- [ ] **Step 5: Inspect the final diff and workspace protection.**

Run: `git diff --check` and `git status --short`. Confirm no unrelated modified/untracked files were staged, overwritten or reverted. Report the exact test counts from pytest output.
