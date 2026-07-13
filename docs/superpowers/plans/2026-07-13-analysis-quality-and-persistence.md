# Analysis Quality And Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make risk, keywords, sentiment, heat and event metadata explainable, persistent and consistent without adding unverified mandatory models.

**Architecture:** Separate pure feature calculation from database orchestration. Persist expensive LLM results at event-update time and expose algorithm method/version/limitations through existing event contracts.

**Tech Stack:** Python, jieba/TF-IDF, optional BGE, OpenAI-compatible LLM, SnowNLP fallback, SQLAlchemy, pytest.

---

### Task 1: Replace event-wide platform punishment with article-level corroboration

**Files:**
- Modify: `backend/app/analysis/fake_detector.py`
- Modify: `backend/tests/test_fake_detector.py`

- [x] **Step 1: Add failing corroboration cases**

Add context fields `corroboration_by_article` and tests proving:

```python
ctx = self._make_event_context(
    platforms={"weibo"},
    corroboration_by_article={1: {"weibo", "zhihu"}},
)
result = assess_suspicious_risk(article, ctx)
self.assertNotIn("缺少跨平台佐证", result["reason"])
```

Also assert a genuinely uncorroborated single-platform article receives the risk feature.

- [x] **Step 2: Run and verify RED**

```powershell
python -m pytest backend/tests/test_fake_detector.py -q
```

- [x] **Step 3: Build article-level corroboration evidence**

Use explicit duplicate group/content hash first, then cross-platform high-similarity shared-entity matches. Store platform count and evidence article IDs in context keyed by article ID.

- [x] **Step 4: Return structured feature evidence**

Keep legacy `score`, `reason`, `method`, `is_suspicious`, and add `feature_scores`, `evidence`, `limitations`, `rule_version`.

- [x] **Step 5: Run tests and commit**

```powershell
python -m pytest backend/tests/test_fake_detector.py -q
git add backend/app/analysis/fake_detector.py backend/tests/test_fake_detector.py
git commit -m "fix: 改为文章级可疑信息交叉验证" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2: Make title-content consistency short-title aware and encoder-pluggable

**Files:**
- Modify: `backend/app/analysis/fake_detector.py`
- Modify: `backend/tests/test_fake_detector.py`

- [x] **Step 1: Add failing cases**

Assert `台风登陆` versus a paragraph describing台风登陆 is consistent despite a short title; assert an unrelated concert body remains inconsistent. Add an injected semantic-similarity provider test.

- [x] **Step 2: Run and verify RED**

- [x] **Step 3: Implement hybrid consistency**

```python
def title_content_consistency(title, content, semantic_similarity=None):
    if semantic_similarity is not None:
        return clamp(semantic_similarity(title, content))
    title_tokens = meaningful_tokens(title)
    body_tokens = meaningful_tokens(content[:800])
    if not title_tokens or not body_tokens:
        return None
    return len(title_tokens & body_tokens) / len(title_tokens)
```

Use a configurable threshold and return `None` for insufficient text.

- [x] **Step 4: Run and commit**

Run the full fake-detector suite and commit.

### Task 3: Use continuous risk features and a bounded LLM gray zone

**Files:**
- Modify: `backend/app/analysis/fake_detector.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_fake_detector.py`

- [x] **Step 1: Add tests for continuous feature output and LLM thresholds**

Assert all feature values are between 0 and 1, final score is 0～100, and LLM is called only when the rule score is within configured gray-zone bounds.

- [x] **Step 2: Run and verify RED**

- [x] **Step 3: Implement versioned feature weights**

Use a config dictionary such as:

```python
RISK_FEATURE_WEIGHTS = {
    "source_traceability": 0.20,
    "cross_platform_corroboration": 0.20,
    "title_content_consistency": 0.15,
    "interaction_anomaly": 0.15,
    "sensationalism": 0.15,
    "advertising_or_external_link": 0.15,
}
```

Score is the weighted feature sum × 100. Mark these as empirical configuration, not trained probabilities.

- [x] **Step 4: Implement structured LLM review**

Only scores within `RISK_LLM_MIN_SCORE` and `RISK_LLM_MAX_SCORE` call the LLM. Parse JSON, append evidence, and never erase explicit rule evidence.

- [x] **Step 5: Run and commit**

Run fake-detector and event-service tests, then commit.

### Task 4: Fix event summary keyword input and preserve query terms with lower weight

**Files:**
- Modify: `backend/app/services/event_aggregation_service.py`
- Modify: `backend/app/services/event_service.py`
- Modify: `backend/tests/test_event_aggregation_service.py`
- Modify: `backend/tests/test_content_analysis_features.py`

- [x] **Step 1: Add failing tests**

Add a test that `_ai_generate_summary()` receives either an Event or a keyword payload, never an Article passed to `_event_keywords`. Add a keyword test asserting the exact query term remains present with `source="query"` and reduced weight rather than deletion.

- [x] **Step 2: Run and verify RED**

- [x] **Step 3: Change summary signature**

```python
def _ai_generate_summary(title, articles, platform_count, *, event_keywords=None):
    keywords = (event_keywords or {}).get("keywords", [])
```

The caller loads `_event_keywords(event)` once and passes the payload explicitly.

- [x] **Step 4: Change query-term handling**

Keep query keywords, cap their normalized display score below the highest event-specific term, and retain `source="query"`.

- [x] **Step 5: Run tests and commit**

Run content-analysis feature and aggregation service suites, then commit.

### Task 5: Add batched LLM keyword extraction with deterministic fallback

**Files:**
- Modify: `backend/app/analysis/llm_keywords.py`
- Modify: `backend/app/services/content_analysis_service.py`
- Create or modify: `backend/tests/test_llm_keywords.py`

- [ ] **Step 1: Add parser and batching tests**

Use a fake client returning a JSON object keyed by article ID. Assert batches respect `LLM_KEYWORD_BATCH_SIZE`, invalid entries are ignored, and missing article IDs use TF-IDF fallback.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Implement injected-client batching**

```python
def extract_keywords_llm(documents, max_per_doc=8, *, client=None, batch_size=5):
    for batch in batched(valid_documents, batch_size):
        response = (client or _llm_client()).chat(...)
        merge parsed results by article_id
```

Never place API keys or raw request headers in warnings.

- [ ] **Step 4: Run content-analysis and keyword tests**

- [ ] **Step 5: Commit**

Commit keyword implementation and tests.

### Task 6: Cap sentiment spread weight and remove the second summary LLM call

**Files:**
- Modify: `backend/app/analysis/sentiment_aggregator.py`
- Modify: `backend/app/services/sentiment_analysis_service.py`
- Modify: `backend/tests/test_sentiment_algorithms.py`
- Modify: `backend/tests/test_sentiment_service.py`

- [ ] **Step 1: Add failing tests**

Assert the hottest article's spread factor is at most 1.5. Add a fake LLM client call counter and assert event summary generation does not cause an additional chat call after article analysis.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Cap the factor**

```python
spread_factor = min(1.5, 1.0 + normalized_log_heat * 0.5)
```

- [ ] **Step 4: Generate deterministic snapshot summary**

Build one sentence from dominant label, weighted ratios, average score and the top representative reasons. Store it inside `calculation_details` or the report payload without calling LLM again.

- [ ] **Step 5: Mark SnowNLP domain fallback**

Add `DOMAIN_MISMATCH_FALLBACK` and enforce the configured confidence cap. Keep a provider interface for an optional transformer, but do not add a mandatory model.

- [ ] **Step 6: Run tests and commit**

```powershell
python -m pytest backend/tests/test_sentiment_algorithms.py backend/tests/test_sentiment_service.py -q
```

Commit after green.

### Task 7: Persist event metadata and forbid detail-read LLM calls

**Files:**
- Modify: `backend/app/models/event.py`
- Modify: `backend/app/llm/prompts.py`
- Modify: `backend/app/services/event_service.py`
- Modify: `backend/app/services/event_aggregation_service.py`
- Modify: `backend/migrations/20260713_event_maturity.sql`
- Modify: `backend/migrations/migrate_event_maturity.py`
- Modify: `backend/tests/test_event_aggregation_service.py`
- Modify or create: `backend/tests/test_event_service.py`

- [ ] **Step 1: Add failing persistence and no-read-side-effect tests**

Publish/update an event with a fake LLM, assert metadata fields and version are stored. Then reset the fake call counter, call `get_event_detail()` twice, and assert zero additional calls and no database writes.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Add metadata fields**

```python
metadata_status = db.Column(db.String(24), nullable=False, default="pending")
metadata_version = db.Column(db.String(32))
metadata_confidence = db.Column(db.Float, nullable=False, default=0.0)
metadata_evidence = db.Column(db.JSON)
metadata_updated_at = db.Column(db.DateTime)
```

- [ ] **Step 4: Replace the prompt with strict JSON**

Require `time_code`, `location`, `key_figures`, `cause`, per-field confidence and evidence article IDs. Reject Markdown wrappers after deterministic cleanup if JSON remains invalid.

- [ ] **Step 5: Generate metadata during publication/update**

Use `first_publish_time` as authoritative time fallback. Preserve existing non-empty metadata when LLM parsing fails.

- [ ] **Step 6: Make detail serialization read-only and run tests**

Run aggregation, event, QA and report tests.

- [ ] **Step 7: Commit**

Commit schema, migration, prompts, services and tests.

### Task 8: Create heat snapshots for search-published events

**Files:**
- Modify: `backend/app/analysis/heat_calculator.py`
- Modify: `backend/app/services/event_aggregation_service.py`
- Modify: `backend/app/services/hotspot_service.py`
- Modify: `backend/tests/test_event_aggregation_service.py`
- Modify: `backend/tests/test_hotspot_service.py`

- [ ] **Step 1: Add a failing publication test**

Publish a search cluster without a HotspotRun and assert:

```python
self.assertIsNotNone(event.current_heat_snapshot_id)
self.assertIsNotNone(event.spread_heat)
self.assertGreater(event.heat_index, 0)
```

Add a time-decay comparison asserting an otherwise equal old event scores below a recent event.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Extract a single-event heat calculation path**

Reuse `heat_calculator` components for one event. Normalize interactions robustly with `log1p`, include report/platform counts, growth when available, and exponential half-life decay.

- [ ] **Step 4: Persist a real `EventHeatSnapshot`**

Save raw statistics, component scores, weights, `formula_version`, time confidence and warnings. Point Event summary fields to the new snapshot.

- [ ] **Step 5: Run tests and commit**

Run hotspot and aggregation suites, then commit.

### Task 9: Full analysis-quality regression and documentation

**Files:**
- Modify: `docs/backend_algorithm_audit.md`
- Modify: `docs/integration_report.md`
- Modify: `docs/后端系统现状与接口说明.md`

- [ ] **Step 1: Run analysis-focused suites**

```powershell
python -m pytest backend/tests/test_fake_detector.py backend/tests/test_content_analysis_features.py backend/tests/test_content_analysis_service.py backend/tests/test_sentiment_algorithms.py backend/tests/test_sentiment_service.py backend/tests/test_event_aggregation_service.py backend/tests/test_hotspot_service.py -q
```

- [ ] **Step 2: Run full automated suite**

```powershell
python -m pytest backend/tests tests -q
```

- [ ] **Step 3: Update documents with exact evidence**

Mark each audit issue as fixed, partially addressed or deliberately replaced, with test names and limitations. Record the exact full-suite result.

- [ ] **Step 4: Commit**

Commit only after fresh verification output is available.
