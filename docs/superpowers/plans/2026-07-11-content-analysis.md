# Content Analysis Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved content analysis module: run-scoped TF-IDF/Bag-of-Words features, structured article/event keywords, persistent analysis-run snapshots, optional BGE cache, background task/API entry points, migrations, and tests.

**Architecture:** Pure analysis code lives under `backend/app/analysis` and has no Flask/database dependency. `content_analysis_service.py` owns snapshot selection, idempotence, persistence, and orchestration. SQLAlchemy models persist run metadata and article-keyword results, while full sparse matrices remain in memory. Existing preprocessing output is consumed without modifying its cleaning or segmentation responsibilities.

**Tech Stack:** Python 3, Flask, Flask-SQLAlchemy, scikit-learn, scipy sparse matrices, jieba TextRank, optional sentence-transformers/BGE, unittest/pytest-compatible tests, MySQL 8 and SQLite test database.

---

## File map

**Create**

- `backend/app/analysis/feature_config.py` — immutable/versioned feature configuration and hash.
- `backend/app/analysis/result.py` — input/result dataclasses and content-analysis exceptions.
- `backend/app/analysis/feature_matrix.py` — shared vocabulary, unweighted count matrix, weighted TF-IDF matrix, small-corpus handling.
- `backend/app/analysis/keyword_extractor.py` — article keywords, TextRank fallback, phrase suppression, event keyword aggregation.
- `backend/app/analysis/embedding.py` — lazy optional BGE encoder abstraction.
- `backend/app/models/analysis_run.py` — `AnalysisRun` and `AnalysisRunArticle` models.
- `backend/app/models/article_embedding.py` — versioned cached article embedding model.
- `backend/app/services/content_analysis_service.py` — create/reuse snapshots and execute analysis.
- `backend/app/api/analysis.py` — create/list/detail analysis-run endpoints.
- `backend/migrations/20260711_content_analysis.sql` — MySQL schema migration.
- `backend/migrations/migrate_content_analysis.py` — migration runner.
- `backend/tests/test_content_analysis_features.py` — pure algorithm tests.
- `backend/tests/test_content_analysis_service.py` — persistence, idempotence, task and API tests.
- `backend/tests/test_content_analysis_migration.py` — model/migration contract tests.

**Modify**

- `backend/app/analysis/__init__.py` — export public analysis types/functions.
- `backend/app/models/__init__.py` — import new SQLAlchemy models before `db.create_all()`.
- `backend/app/services/analysis_service.py` — replace placeholder with content-analysis delegation.
- `backend/app/tasks/jobs.py` — implement `analyze_job` with task progress and lease-safe service call.
- `backend/app/tasks/runner.py` — register `analysis` for recovery.
- `backend/app/api/__init__.py` — register analysis blueprint.
- `backend/app/core/config.py` — feature/BGE settings.
- `backend/.env.example` — document settings.
- `backend/requirements.txt` — add scikit-learn/scipy and optional embedding dependency.
- `backend/migrations/README.md` — document migration order.

---

### Task 1: Feature configuration and matrix builder

**Files:**
- Create: `backend/app/analysis/feature_config.py`
- Create: `backend/app/analysis/result.py`
- Create: `backend/app/analysis/feature_matrix.py`
- Modify: `backend/app/analysis/__init__.py`
- Test: `backend/tests/test_content_analysis_features.py`

- [ ] **Step 1: Write failing tests for pre-tokenized unigrams/bigrams, shared title/body vocabulary, weighted counts, normal corpus, small corpus, one-document fallback, and empty vocabulary.**

Use `AnalysisDocument(article_id, title, title_tokens, body_tokens, ...)` fixtures. Assert `feature_names` contains `官方 通报`, `count_matrix` contains integer combined counts, `tfidf_matrix` is L2 normalized, changing `title_weight` changes weighted counts, 2–4 documents emit `SMALL_CORPUS`, one document returns `matrix=None` with fallback status, and zero documents raises `NoValidDocumentError`.

- [ ] **Step 2: Run the focused tests and verify they fail because the modules do not exist.**

Run: `python -m pytest backend/tests/test_content_analysis_features.py -v`

Expected: import/collection failure for `app.analysis.feature_matrix`.

- [ ] **Step 3: Implement immutable configuration and typed results.**

`FeatureConfig` must expose the approved defaults (`5000`, `(1, 2)`, `min_df=1`, `max_df=.90`, title/body `1.0`, keyword limits `10/20`, minimum normal documents `5`) and a stable SHA-256 `config_hash()` generated from sorted JSON.

`AnalysisDocument` must contain article/snapshot identity, title/body tokens, platform, entities/topics, `nlp_weight`, and warnings. `FeatureMatrixResult` must contain document order, feature names, unweighted count matrix, weighted count matrix, TF-IDF matrix, warnings, and statistics.

- [ ] **Step 4: Implement the matrix builder.**

Fit one `CountVectorizer` vocabulary on pre-tokenized combined title/body documents using identity analyzer semantics. Transform title and body independently, return unweighted integer combined counts for LDA, calculate `title_weight * title_counts + body_weight * body_counts`, then apply `TfidfTransformer(norm="l2", smooth_idf=True, sublinear_tf=True)`.

For 2–4 documents force effective `max_df=1.0` and append `SMALL_CORPUS`. For one document return a fallback result without a corpus TF-IDF matrix. Convert sklearn empty-vocabulary errors to `EmptyVocabularyError`.

- [ ] **Step 5: Run focused tests and verify they pass.**

Run: `python -m pytest backend/tests/test_content_analysis_features.py -v`

Expected: matrix/config tests pass.

---

### Task 2: Structured keyword extraction

**Files:**
- Create: `backend/app/analysis/keyword_extractor.py`
- Modify: `backend/app/analysis/result.py`
- Modify: `backend/app/analysis/__init__.py`
- Test: `backend/tests/test_content_analysis_features.py`

- [ ] **Step 1: Add failing tests for article keyword limits, score normalization, TextRank fill-only behavior, entity/query retention, phrase-over-unigram preference, and event keyword coverage.**

Patch the TextRank adapter so tests do not depend on jieba scoring. Assert article keywords contain `term/score/rank/source/type`, never exceed 10, and remain within `[0, 1]`. Assert event aggregation honors `nlp_weight`, reports `document_count/document_ratio/platform_count`, and normally excludes a term occurring in only one article.

- [ ] **Step 2: Run the focused tests and verify the new cases fail.**

Run: `python -m pytest backend/tests/test_content_analysis_features.py -v`

Expected: missing keyword functions/result types.

- [ ] **Step 3: Implement article keyword extraction.**

Read nonzero TF-IDF values, normalize feature names by NFKC/case/space rules, reject pure numbers/template terms/meaningless single characters, merge explicit aliases, infer `word/phrase/person/location/organization/hashtag` types, suppress low-information unigrams covered by stronger bigrams, preserve query/topic/entity candidates, and use `jieba.analyse.textrank` only when valid TF-IDF candidates are fewer than the limit.

- [ ] **Step 4: Implement event keyword aggregation.**

Accept an event-to-document-index mapping and aggregate TF-IDF values using each document's `nlp_weight`. Track document and platform coverage, allow entity/topic exceptions to the two-document rule, normalize event scores, and return at most 20 items.

- [ ] **Step 5: Run focused tests and verify they pass.**

Run: `python -m pytest backend/tests/test_content_analysis_features.py -v`

Expected: all pure feature and keyword tests pass.

---

### Task 3: Analysis-run persistence models and migration

**Files:**
- Create: `backend/app/models/analysis_run.py`
- Create: `backend/app/models/article_embedding.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/20260711_content_analysis.sql`
- Create: `backend/migrations/migrate_content_analysis.py`
- Modify: `backend/migrations/README.md`
- Test: `backend/tests/test_content_analysis_migration.py`

- [ ] **Step 1: Write failing schema tests.**

Create an in-memory Flask app, run `db.create_all()`, and assert tables `analysis_run`, `analysis_run_article`, and `article_embedding` exist. Compile MySQL DDL and assert JSON columns, foreign keys, unique constraints, status/index columns, and embedding version uniqueness are present. Test the migration statement splitter and reject non-MySQL URLs.

- [ ] **Step 2: Run migration tests and verify failure.**

Run: `python -m pytest backend/tests/test_content_analysis_migration.py -v`

Expected: model imports/tables are missing.

- [ ] **Step 3: Implement SQLAlchemy models.**

`AnalysisRun` stores user/mode/keyword/platforms, fingerprints, dataset/config hashes, counts, config/version JSON, status/warnings/error, and timestamps. `AnalysisRunArticle` stores run/article/snapshot/content-version identity, representative flag, NLP weight, feature status, keywords, warnings, with a unique `(analysis_run_id, article_id)` constraint. `ArticleEmbedding` stores article/snapshot/content version, model/preprocess version, dimension and JSON vector with a versioned uniqueness constraint.

- [ ] **Step 4: Implement MySQL migration and runner.**

Use the existing migration style: explicit SQL file, semicolon splitter, `create_engine`, and MySQL-only guard. Add indexes for user/status/created time, run/article joins, and embedding lookup.

- [ ] **Step 5: Run migration tests and existing persistence tests.**

Run: `python -m pytest backend/tests/test_content_analysis_migration.py backend/tests/test_persistence.py -v`

Expected: both suites pass.

---

### Task 4: Content analysis service

**Files:**
- Create: `backend/app/services/content_analysis_service.py`
- Modify: `backend/app/services/analysis_service.py`
- Test: `backend/tests/test_content_analysis_service.py`

- [ ] **Step 1: Write failing service tests.**

Create valid, duplicate, advertisement, failed, title-only and low-quality articles with `DocumentFeatures`. Test snapshot creation, representative selection, dataset hash stability, idempotent reuse, run-specific keyword persistence, no writes to `DocumentFeatures.tfidf_vector`, one-document fallback, empty input failure, and rollback on `DATASET_CHANGED`.

- [ ] **Step 2: Run service tests and verify failure.**

Run: `python -m pytest backend/tests/test_content_analysis_service.py -v`

Expected: missing service/models.

- [ ] **Step 3: Implement `create_analysis_run`.**

Validate mode/platforms/article IDs, load requested articles and features, create `AnalysisRunArticle` rows for requested items, mark duplicates/ads/failed/empty-token items as skipped, compute stable snapshot identity and dataset hash, and reuse an existing successful run only when dataset/config/query fingerprints match.

- [ ] **Step 4: Implement `run_content_analysis`.**

Lock the run, verify snapshots/content versions, mark `running`, segment titles with the existing versioned segmenter, create `AnalysisDocument` objects, build features, extract and persist article keywords, save statistics/warnings/config versions, commit `success`, and convert known failures into `failed` runs with explicit codes. Never persist sparse vectors.

- [ ] **Step 5: Implement result serialization and retrieval helpers.**

Return sanitized run metadata, article keyword results and counts without returning internal matrix objects or full article bodies.

- [ ] **Step 6: Run service and algorithm tests.**

Run: `python -m pytest backend/tests/test_content_analysis_features.py backend/tests/test_content_analysis_service.py -v`

Expected: both suites pass.

---

### Task 5: Optional BGE encoder and cache

**Files:**
- Create: `backend/app/analysis/embedding.py`
- Modify: `backend/app/services/content_analysis_service.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_content_analysis_features.py`
- Test: `backend/tests/test_content_analysis_service.py`

- [ ] **Step 1: Write failing tests using a fake encoder.**

Assert embeddings are normalized, cached by article/content/model/preprocess version, reused without a second encode call, model failures append `BGE_UNAVAILABLE`, and TF-IDF/keyword completion still succeeds.

- [ ] **Step 2: Run focused tests and verify failure.**

Run: `python -m pytest backend/tests/test_content_analysis_features.py backend/tests/test_content_analysis_service.py -v`

Expected: embedding adapter/cache behavior missing.

- [ ] **Step 3: Implement lazy optional encoder.**

Load `SentenceTransformer` only on first use, default to `BAAI/bge-small-zh-v1.5`, encode title plus bounded clean text with normalized embeddings, expose an injectable encoder interface for tests, and raise `EmbeddingUnavailableError` without failing the primary analysis.

- [ ] **Step 4: Add configuration and dependencies.**

Add BGE enable/model/preprocess/text-length settings. Add compatible scikit-learn/scipy versions as required dependencies; keep sentence-transformers optional at runtime through lazy import while documenting it in requirements for full BGE support.

- [ ] **Step 5: Run focused tests and verify pass.**

Run: `python -m pytest backend/tests/test_content_analysis_features.py backend/tests/test_content_analysis_service.py -v`

Expected: BGE tests pass without downloading a real model.

---

### Task 6: Background task and API integration

**Files:**
- Create: `backend/app/api/analysis.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/app/tasks/runner.py`
- Test: `backend/tests/test_content_analysis_service.py`

- [ ] **Step 1: Write failing task/API tests.**

Test authenticated `POST /api/analysis/runs` with explicit article IDs and optional keyword/platform metadata, `GET /api/analysis/runs`, `GET /api/analysis/runs/<id>`, ownership/admin access, invalid empty platform selection in search mode, background task creation, analyze-job progress, successful result containing `analysis_run_id`, and recovery registry support for `analysis` tasks.

- [ ] **Step 2: Run API/task tests and verify failure.**

Run: `python -m pytest backend/tests/test_content_analysis_service.py -v`

Expected: blueprint/job/recovery entries missing.

- [ ] **Step 3: Implement the analysis blueprint.**

Create or reuse a run, create an `analysis` task carrying `analysis_run_id`, submit it through the existing runner, and expose owned run summaries/details. Never expose article bodies, vectors, API credentials, or other users' runs.

- [ ] **Step 4: Implement `analyze_job` and recovery registration.**

Use `get_task/update_task`, report staged progress, call `run_content_analysis`, set terminal task status/result, and register `analysis` alongside crawl/import in `recover_background_jobs`.

- [ ] **Step 5: Run API/task tests and existing task tests.**

Run: `python -m pytest backend/tests/test_content_analysis_service.py backend/tests/test_jobs.py backend/tests/test_crawler_api.py -v`

Expected: all pass.

---

### Task 7: Full verification and documentation sync

**Files:**
- Modify only if tests reveal a real issue: files from Tasks 1–6.

- [ ] **Step 1: Run content-analysis tests.**

Run: `python -m pytest backend/tests/test_content_analysis_features.py backend/tests/test_content_analysis_service.py backend/tests/test_content_analysis_migration.py -v`

Expected: zero failures.

- [ ] **Step 2: Run all backend tests.**

Run: `python -m pytest backend/tests -v`

Expected: zero failures; crawler/preprocessing/auth/task behavior remains intact.

- [ ] **Step 3: Run syntax compilation.**

Run: `python -m compileall backend/app backend/migrations`

Expected: exit code 0 with no syntax errors.

- [ ] **Step 4: Verify migration and git diff hygiene.**

Run: `git diff --check` and `git status --short`.

Expected: no whitespace errors; only intended content-analysis files plus the user's pre-existing unrelated changes remain.

- [ ] **Step 5: Commit only content-analysis implementation files.**

Stage exact paths from this plan, inspect `git diff --cached --name-only`, and commit without including unrelated dirty-worktree files.

