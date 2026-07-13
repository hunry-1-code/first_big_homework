# Backend Baseline And Contract Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the currently broken content-analysis pipeline, remove its downstream failure cascade, and align backend defaults and API enums with the approved v2 contract.

**Architecture:** Keep algorithm-domain objects inside `app.analysis`, but convert them to JSON-safe dictionaries at the service persistence boundary. Establish one authoritative set of aggregation defaults and one authoritative Chinese enum mapping before changing higher-level algorithms.

**Tech Stack:** Python 3, Flask, SQLAlchemy, unittest/pytest, SQLite test database.

---

### Task 1: Persist JSON-safe article keywords before any database flush

**Files:**
- Modify: `backend/app/services/content_analysis_service.py`
- Modify: `backend/tests/test_content_analysis_service.py`

- [x] **Step 1: Strengthen the failing persistence test**

Add JSON serialization assertions after the existing keyword persistence assertions:

```python
import json

for row in rows:
    json.dumps(row.keywords, ensure_ascii=False)
    self.assertTrue(all(isinstance(item, dict) for item in row.keywords))
    self.assertTrue(all("term" in item and "score" in item for item in row.keywords))
```

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_content_analysis_service.py::ContentAnalysisServiceTest::test_run_analysis_persists_run_specific_keywords_without_vectors backend/tests/test_content_analysis_service.py::ContentAnalysisServiceTest::test_embedding_is_cached_and_failure_only_adds_warning -q
```

Expected: JSON persistence fails with `ArticleKeyword is not JSON serializable`; encoder call count remains zero.

- [x] **Step 3: Add one JSON-boundary conversion helper**

Add near the service helpers:

```python
def _json_keywords(items) -> list[dict]:
    output = []
    for item in items or []:
        if hasattr(item, "as_dict"):
            output.append(item.as_dict())
        elif isinstance(item, dict):
            output.append(dict(item))
        else:
            raise TypeError(f"unsupported keyword value: {type(item).__name__}")
    return output
```

Immediately after LLM/TF-IDF merging, build a JSON-safe map:

```python
json_keyword_map = {
    article_id: _json_keywords(items)
    for article_id, items in keyword_map.items()
}
```

Assign `row.keywords` only from `json_keyword_map` in both the normal path and BGE rollback path.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the same command. Expected: both tests pass; `encoder.calls == 1`.

- [x] **Step 5: Run the whole content-analysis service suite**

```powershell
python -m pytest backend/tests/test_content_analysis_service.py -q
```

Expected: all tests pass.

- [x] **Step 6: Commit**

```powershell
git add backend/app/services/content_analysis_service.py backend/tests/test_content_analysis_service.py
git commit -m "fix: 修复内容分析关键词持久化与BGE调用" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2: Confirm downstream jobs recover after the upstream fix

**Files:**
- Test: `backend/tests/test_crawler_api.py`
- Test: `backend/tests/test_hotspot_service.py`
- Test: `backend/tests/test_jobs.py`

- [x] **Step 1: Run direct downstream suites**

```powershell
python -m pytest backend/tests/test_crawler_api.py backend/tests/test_hotspot_service.py backend/tests/test_jobs.py -q
```

Expected: failures caused by JSON serialization disappear. Record any remaining independent failure by exact test name and traceback.

- [x] **Step 2: For every remaining independent failure, add or isolate its reproducer**

Do not edit production code until the failure is reduced to one focused test. The new test must fail for the observed independent reason, not for content-analysis serialization.

- [x] **Step 3: Apply the minimum independent fix**

Use the root-cause evidence from Step 2. Do not change hotspot formulas, clustering thresholds or task semantics in this baseline task.

- [x] **Step 4: Re-run the downstream suites**

Expected: all three suites pass before proceeding.

- [x] **Step 5: Record the verification result**

If all failures disappear, proceed without a code commit. If a new independent failure appears, stop this task and insert a new focused TDD task into this plan before editing production code.

### Task 3: Align public enum mappings with the approved v2 contract

**Files:**
- Modify: `backend/app/services/api_contract_service.py`
- Modify: `backend/tests/test_contracts.py`
- Modify: `docs/backend_api_data_format.md`

- [x] **Step 1: Change the contract test to the approved values**

Replace stale expectations with:

```python
self.assertEqual(api_lifecycle_stage("高潮期"), "高潮期")
self.assertEqual(api_sentiment_label("neutral"), "中立")
self.assertEqual(api_sentiment_label("中性"), "中立")
```

Add invalid-value fallbacks:

```python
self.assertEqual(api_lifecycle_stage("爆发期"), "潜伏期")
self.assertEqual(api_sentiment_label("unknown"), "中立")
```

- [x] **Step 2: Run the contract test and verify RED**

```powershell
python -m pytest backend/tests/test_contracts.py::ApiOutputContractTest::test_maps_contract_enums_and_values -q
```

Expected: current code returns `中性` for neutral sentiment.

- [x] **Step 3: Implement the canonical mapping**

Use readable constants rather than one-line functions:

```python
LIFECYCLE_STAGES = {"潜伏期", "成长期", "高潮期", "消退期"}
SENTIMENT_LABELS = {
    "positive": "正面",
    "正面": "正面",
    "negative": "负面",
    "负面": "负面",
    "neutral": "中立",
    "中立": "中立",
    "中性": "中立",
}
```

`api_lifecycle_stage()` returns the input only when it is canonical. `api_sentiment_label()` defaults to `中立`.

- [x] **Step 4: Run contract tests**

```powershell
python -m pytest backend/tests/test_contracts.py -q
```

Expected: all pass.

- [x] **Step 5: Update stale API examples**

In `docs/backend_api_data_format.md`, replace `爆发期` with `高潮期` and `中性` with `中立`, and mark the document as aligned to the v2 contract date.

- [x] **Step 6: Commit**

```powershell
git add backend/app/services/api_contract_service.py backend/tests/test_contracts.py docs/backend_api_data_format.md
git commit -m "fix: 统一生命周期与情感接口枚举" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 4: Establish one authoritative aggregation default configuration

**Files:**
- Modify: `backend/app/analysis/aggregation_config.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_event_aggregation_algorithms.py`

- [x] **Step 1: Update the test to the approved tuned defaults**

Use:

```python
self.assertEqual(first.attach_threshold, 0.55)
self.assertEqual(first.create_threshold, 0.40)
self.assertEqual(first.move_margin, 0.10)
self.assertEqual(first.bge_weight, 0.55)
self.assertEqual(first.tfidf_weight, 0.20)
self.assertEqual(first.entity_weight, 0.15)
self.assertEqual(first.time_weight, 0.10)
```

Assert `Config` exposes identical values.

- [x] **Step 2: Run and verify RED**

```powershell
python -m pytest backend/tests/test_event_aggregation_algorithms.py::AggregationConfigTest -q
```

Expected: dataclass and application defaults disagree.

- [x] **Step 3: Change the dataclass defaults and example environment**

Set `AggregationConfig` defaults to the values above. Keep `Config` environment overrides, and update `.env.example` to the same defaults. Do not read or modify `backend/.env`.

- [x] **Step 4: Run aggregation algorithm tests**

```powershell
python -m pytest backend/tests/test_event_aggregation_algorithms.py -q
```

Expected: all current algorithm tests pass.

- [x] **Step 5: Commit**

```powershell
git add backend/app/analysis/aggregation_config.py backend/app/core/config.py backend/.env.example backend/tests/test_event_aggregation_algorithms.py
git commit -m "fix: 统一事件聚合默认配置" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 5: Verify the restored baseline and update the recorded result

**Files:**
- Modify: `docs/integration_report.md`
- Modify: `docs/后端系统现状与接口说明.md`

- [ ] **Step 1: Run the full automated suite**

```powershell
python -m pytest backend/tests tests -q
```

Expected at this phase: serialization cascade, contract mismatch and configuration mismatch are gone. Propagation and lifecycle failures remain intentionally red for the next plan.

- [ ] **Step 2: Record the exact result without claiming full completion**

Add the command, pass/fail counts and remaining test names to the integration report. Replace stale `263 passed` text in the backend status document with the fresh result and a dated note.

- [ ] **Step 3: Commit**

```powershell
git add docs/integration_report.md docs/后端系统现状与接口说明.md
git commit -m "docs: 更新后端基线修复测试结果" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```
