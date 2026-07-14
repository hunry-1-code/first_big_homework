# Comment Crawling And Public Opinion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add independently persisted comments/replies/danmaku for Zhihu, Weibo, Douyin and Bilibili, then expose comment-derived public-opinion analysis without feeding comments into event clustering.

**Architecture:** Keep `Article` as the event-discovery unit and add a separate `Comment` aggregate attached to articles. Platform adapters fetch comments in a second stage, a comment service normalizes/persists/analyzes them, and event serialization returns a public-opinion snapshot with explicit coverage and institutional-data degradation states.

**Tech Stack:** Flask 3, Flask-SQLAlchemy, SQLite/MySQL migrations, requests-based crawler adapters, jieba/SnowNLP/DeepSeek-compatible sentiment, unittest/pytest.

---

## File map

**Create:**

- `backend/app/models/comment.py`: comment/reply/danmaku persistence model.
- `backend/app/crawler/comments.py`: `RawComment`, comment batch and adapter protocol.
- `backend/app/crawler/tikhub_comments.py`: Zhihu/Weibo/Douyin TikHub comment endpoints and mappings.
- `backend/app/services/comment_service.py`: comment cleaning, upsert, sampling and analysis.
- `backend/app/services/public_opinion_service.py`: event-level public opinion and narrative coverage snapshot.
- `backend/migrations/20260714_comments_and_source_layers.sql`: MySQL schema changes.
- `backend/migrations/migrate_comments_and_source_layers.py`: SQLite/MySQL migration runner.
- `backend/tests/test_comment_migration.py`: migration coverage.
- `backend/tests/test_comment_adapters.py`: platform mapping and pagination coverage.
- `backend/tests/test_comment_service.py`: persistence, analysis and failure isolation.
- `backend/tests/test_public_opinion_service.py`: public-only and comparable narrative modes.

**Modify:**

- `backend/app/models/__init__.py`: export `Comment`.
- `backend/app/models/article.py`: add `source_layer` and `source_role`.
- `backend/app/crawler/bilibili.py`: video/column body support and public comment/reply/danmaku fetch methods.
- `backend/app/crawler/factory.py`: construct TikHub comment adapters with platform-specific keys.
- `backend/app/core/config.py`: comment and danmaku configuration.
- `backend/app/tasks/jobs.py`: run comment enrichment after article persistence and after event publication.
- `backend/app/services/event_service.py`: attach public-opinion snapshot to event details.
- `backend/.env`: add empty API-key placeholders and limits.
- `backend/.env.example`: document the same variables.
- `backend/migrations/README.md`: add migration command.
- `docs/integration_report.md`: record implemented behavior and limitations.

### Task 1: Comment schema, source layers and configuration

**Files:**
- Create: `backend/app/models/comment.py`
- Modify: `backend/app/models/article.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/20260714_comments_and_source_layers.sql`
- Create: `backend/migrations/migrate_comments_and_source_layers.py`
- Test: `backend/tests/test_comment_migration.py`

- [ ] **Step 1: Write migration tests that require Comment and Article source-layer fields**

```python
def test_sqlite_migration_creates_comment_and_source_layer_columns(self):
    migrate(self.database_url)
    inspector = inspect(self.engine)
    self.assertIn("comment", inspector.get_table_names())
    article_columns = {item["name"] for item in inspector.get_columns("article")}
    self.assertTrue({"source_layer", "source_role"}.issubset(article_columns))
```

- [ ] **Step 2: Run the migration test and verify it fails**

Run: `python -m pytest backend/tests/test_comment_migration.py -q`

Expected: FAIL because the migration and model do not exist.

- [ ] **Step 3: Implement the Comment model and migration**

The model must use the table name `comment`, a unique constraint on `(platform, source_comment_id)`, indexes on `article_id`, `parent_comment_id` and `analysis_status`, and nullable self-references for parent/root comments. Add these Article fields:

```python
source_layer = db.Column(db.String(24), nullable=False, default="unknown", server_default="unknown")
source_role = db.Column(db.String(32), nullable=False, default="unknown", server_default="unknown")
```

- [ ] **Step 4: Run the migration test and model-related persistence tests**

Run: `python -m pytest backend/tests/test_comment_migration.py backend/tests/test_persistence.py -q`

Expected: PASS.

- [ ] **Step 5: Commit schema work**

```powershell
git add backend/app/models backend/migrations backend/tests/test_comment_migration.py
git commit -m "新增评论数据模型与信源分层字段" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2: Raw comment contract and deterministic persistence

**Files:**
- Create: `backend/app/crawler/comments.py`
- Create: `backend/app/services/comment_service.py`
- Test: `backend/tests/test_comment_service.py`

- [ ] **Step 1: Write failing tests for RawComment normalization and idempotent upsert**

```python
def test_persist_comment_is_idempotent_and_updates_metrics(self):
    first = persist_comment(self.article, RawComment(platform="weibo", source_comment_id="c1", content="需要及时救援", likes_count=3))
    second = persist_comment(self.article, RawComment(platform="weibo", source_comment_id="c1", content="需要及时救援", likes_count=8))
    self.assertEqual(first.id, second.id)
    self.assertEqual(Comment.query.count(), 1)
    self.assertEqual(second.likes_count, 8)
```

Also cover empty text rejection, stable `content_hash`, reply linkage and `content_kind=danmaku`.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest backend/tests/test_comment_service.py -q`

Expected: FAIL because the contract/service do not exist.

- [ ] **Step 3: Implement minimal comment cleaning and persistence**

Reuse `clean_text`, `segment_text` and `analyze_sentiment`/SnowNLP fallback. Do not call article persistence and do not create `AnalysisRunArticle` rows. Assign comments to `source_layer=public`, `source_role=comment` or `danmaku`.

- [ ] **Step 4: Run comment service and preprocessing regression tests**

Run: `python -m pytest backend/tests/test_comment_service.py backend/tests/test_preprocessing.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the comment contract and service**

```powershell
git add backend/app/crawler/comments.py backend/app/services/comment_service.py backend/tests/test_comment_service.py
git commit -m "实现评论清洗分析与幂等入库" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 3: TikHub adapters for Zhihu, Weibo and Douyin

**Files:**
- Create: `backend/app/crawler/tikhub_comments.py`
- Modify: `backend/app/crawler/factory.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_comment_adapters.py`

- [ ] **Step 1: Write failing adapter tests with local stub payloads**

Cover the exact endpoint families:

```text
/api/v1/zhihu/web/fetch_comment_v5
/api/v1/zhihu/web/fetch_sub_comment_v5
/api/v1/weibo/web_v2/fetch_post_comments
/api/v1/weibo/web_v2/fetch_post_sub_comments
/api/v1/douyin/web/fetch_video_comments
/api/v1/douyin/web/fetch_video_comment_replies
```

Each test must assert comment ID, parent/root ID, text, author, publish time, likes/replies and next cursor.

- [ ] **Step 2: Run adapter tests and verify failure**

Run: `python -m pytest backend/tests/test_comment_adapters.py -q`

Expected: FAIL because `TikHubCommentCrawler` is missing.

- [ ] **Step 3: Implement platform-specific parsers behind one adapter interface**

Use `Authorization: Bearer <platform key>`, keep endpoint paths in a platform configuration map, stop at configured limits, and convert 401/403/429 to stable `CrawlerError` codes. Never include headers or credentials in returned diagnostics.

- [ ] **Step 4: Register platform-specific keys and limits**

Add config values:

```python
TIKHUB_ZHIHU_API_KEY = os.getenv("TIKHUB_ZHIHU_API_KEY", "")
COMMENT_COLLECTION_ENABLED = os.getenv("COMMENT_COLLECTION_ENABLED", "true").lower() == "true"
COMMENT_MAX_PER_ARTICLE = min(200, max(1, int(os.getenv("COMMENT_MAX_PER_ARTICLE", "50"))))
COMMENT_REPLY_LIMIT = min(100, max(0, int(os.getenv("COMMENT_REPLY_LIMIT", "20"))))
```

- [ ] **Step 5: Run adapter and existing crawler tests**

Run: `python -m pytest backend/tests/test_comment_adapters.py backend/tests/test_crawler_adapters.py backend/tests/test_crawler_core.py -q`

Expected: PASS without external network calls.

- [ ] **Step 6: Commit TikHub comment adapters**

```powershell
git add backend/app/crawler/tikhub_comments.py backend/app/crawler/factory.py backend/app/core/config.py backend/tests/test_comment_adapters.py
git commit -m "接入知乎微博抖音评论接口" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 4: Bilibili video, column, comments, replies and danmaku

**Files:**
- Modify: `backend/app/crawler/bilibili.py`
- Test: `backend/tests/test_comment_adapters.py`
- Test: `backend/tests/test_crawler_adapters.py`

- [ ] **Step 1: Add failing Bilibili tests**

Tests must cover video search results, column results, `/x/v2/reply/main` comments, `/x/v2/reply/reply` child replies and danmaku XML parsing. Video documents must use title plus description and append subtitle text only when a public subtitle body is available.

- [ ] **Step 2: Run Bilibili tests and verify failure**

Run: `python -m pytest backend/tests/test_comment_adapters.py -k bilibili -q`

Expected: FAIL because video/comment/danmaku methods are absent.

- [ ] **Step 3: Extend BilibiliCrawler without breaking column behavior**

Use `request.extra["content_type"]` with `video`, `article` and `all`; default to `all`. Implement comment methods that return `CommentBatch`. Danmaku must use `content_kind="danmaku"`, have no parent and obey `DANMAKU_MAX_PER_VIDEO`.

- [ ] **Step 4: Run Bilibili and full adapter tests**

Run: `python -m pytest backend/tests/test_comment_adapters.py backend/tests/test_crawler_adapters.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Bilibili expansion**

```powershell
git add backend/app/crawler/bilibili.py backend/tests/test_comment_adapters.py backend/tests/test_crawler_adapters.py
git commit -m "扩展B站视频评论回复与弹幕采集" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 5: Comment enrichment orchestration and failure isolation

**Files:**
- Modify: `backend/app/tasks/jobs.py`
- Modify: `backend/app/services/comment_service.py`
- Test: `backend/tests/test_jobs.py`
- Test: `backend/tests/test_comment_service.py`

- [ ] **Step 1: Write failing task tests**

Test that article persistence succeeds when comment collection raises 403, that other platforms continue, and that comments do not alter `AnalysisRun.article_count`, `AggregationCluster.member_count` or event `independent_report_count`.

- [ ] **Step 2: Run task tests and verify failure**

Run: `python -m pytest backend/tests/test_jobs.py -k comment -q`

Expected: FAIL because enrichment is not wired.

- [ ] **Step 3: Add post-persistence comment enrichment**

After each supported article is persisted, invoke a bounded comment collection helper when enabled. Store per-platform results under `task.result.comment_collection` with collected, processed, failed and stable errors. Do not fail the parent crawl task solely because comments failed.

- [ ] **Step 4: Run jobs, task and aggregation regressions**

Run: `python -m pytest backend/tests/test_jobs.py backend/tests/test_event_aggregation_service.py backend/tests/test_crawler_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit orchestration**

```powershell
git add backend/app/tasks/jobs.py backend/app/services/comment_service.py backend/tests/test_jobs.py backend/tests/test_comment_service.py
git commit -m "串联正文后的评论补充采集" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 6: Public-opinion and narrative coverage snapshot

**Files:**
- Create: `backend/app/services/public_opinion_service.py`
- Modify: `backend/app/services/event_service.py`
- Test: `backend/tests/test_public_opinion_service.py`
- Test: `backend/tests/test_contracts.py`

- [ ] **Step 1: Write failing public-opinion tests**

Required cases:

```python
def test_public_only_event_does_not_invent_authority_gap(self):
    result = build_public_opinion_snapshot(event_id)
    self.assertEqual(result["institutional_status"], "not_observed")
    self.assertEqual(result["narrative_gap_status"], "authority_not_observed")
    self.assertIsNone(result["narrative_gap_score"])
    self.assertGreater(result["comment_count"], 0)
```

Also test platform sentiment, high-frequency terms, demand phrases and institutional/public comparable mode.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest backend/tests/test_public_opinion_service.py -q`

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement deterministic aggregation**

The first version must use persisted sentiment labels, tokens and interaction weights. Return counts, ratios, platform distribution, top terms, high-interaction comments, institutional/public status and limitations. Only calculate a bounded gap score when both layers meet configured minimum samples.

- [ ] **Step 4: Attach the snapshot to event details**

Add `public_opinion` to `GET /api/events/{id}` without changing existing fields. The endpoint must remain read-only and must not call external APIs or LLMs.

- [ ] **Step 5: Run contract and event tests**

Run: `python -m pytest backend/tests/test_public_opinion_service.py backend/tests/test_contracts.py backend/tests/test_sentiment_service.py -q`

Expected: PASS.

- [ ] **Step 6: Commit public-opinion output**

```powershell
git add backend/app/services/public_opinion_service.py backend/app/services/event_service.py backend/tests/test_public_opinion_service.py backend/tests/test_contracts.py
git commit -m "增加评论驱动的公众意见分析" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 7: Environment templates and documentation

**Files:**
- Modify: `backend/.env`
- Modify: `backend/.env.example`
- Modify: `backend/migrations/README.md`
- Modify: `docs/integration_report.md`

- [ ] **Step 1: Add empty environment settings**

Add only empty key values and numeric/boolean defaults. Never copy values from existing keys:

```dotenv
TIKHUB_ZHIHU_API_KEY=
TIKHUB_WEIBO_API_KEY=
TIKHUB_DOUYIN_API_KEY=
COMMENT_COLLECTION_ENABLED=true
COMMENT_MAX_PER_ARTICLE=50
COMMENT_REPLY_LIMIT=20
DANMAKU_COLLECTION_ENABLED=true
DANMAKU_MAX_PER_VIDEO=100
```

- [ ] **Step 2: Document migration and operational limitations**

Record the migration command, comment limits, per-platform external dependencies, public-only degradation and the fact that comment failure does not fail article analysis.

- [ ] **Step 3: Verify no secrets are staged**

Run: `git diff --cached -- backend/.env backend/.env.example`

Expected: `.env` remains ignored/untracked; `.env.example` contains only empty placeholders.

- [ ] **Step 4: Commit tracked configuration/docs**

```powershell
git add backend/.env.example backend/migrations/README.md docs/integration_report.md
git commit -m "补充评论采集配置与使用说明" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 8: Full verification and review

**Files:**
- Review all modified files.

- [ ] **Step 1: Run focused comment suite**

Run:

```powershell
python -m pytest backend/tests/test_comment_migration.py backend/tests/test_comment_adapters.py backend/tests/test_comment_service.py backend/tests/test_public_opinion_service.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run crawler, jobs, aggregation and sentiment regressions**

Run:

```powershell
python -m pytest backend/tests/test_crawler_core.py backend/tests/test_crawler_adapters.py backend/tests/test_jobs.py backend/tests/test_event_aggregation_service.py backend/tests/test_sentiment_service.py backend/tests/test_contracts.py -q
```

Expected: zero failures.

- [ ] **Step 3: Run full backend and root test suites**

Run: `python -m pytest backend/tests tests -q`

Expected: zero failures; report exact pass/warning/subtest counts rather than reusing historical counts.

- [ ] **Step 4: Run secret and diff checks**

Run:

```powershell
git diff --check
git status --short
git grep -n -I -E "Bearer [A-Za-z0-9._-]{12,}|TIKHUB_[A-Z_]*API_KEY=.+" -- ':!backend/.env'
```

Expected: no whitespace errors, only intended files changed, and no populated keys outside ignored `.env`.

- [ ] **Step 5: Request code review**

Invoke the `requesting-code-review` skill, inspect findings, fix material issues and rerun affected verification commands before claiming completion.
