# Kung Fu Women Football End-to-End Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the real “《功夫女足》电影” keyword through backend crawling, analysis, formal-event publication and the actual Vue frontend, preserving every intermediate state and repairing any user-visible data-quality defect.

**Architecture:** A dedicated Python E2E driver launches an isolated Flask server, drives the official REST APIs, exports model states, launches Vite, verifies the real pages through Selenium/Chrome, and writes sanitized artifacts. The production development database and credentials remain untouched.

**Tech Stack:** Flask, SQLAlchemy, SQLite, requests, Vue 3, Vite, npm, Selenium, Chrome, pytest, Markdown.

---

### Task 1: Build the E2E driver core with TDD

**Files:**
- Create: `tools/run_keyword_e2e.py`
- Create: `tests/test_run_keyword_e2e.py`
- Reuse: `tools/validate_backend_live.py`

- [x] **Step 1: Write failing pure behavior tests**

Test:

```python
from tools.run_keyword_e2e import (
    assess_frontend_data_quality,
    choose_relevant_cluster,
    safe_artifact,
)


def test_cluster_selection_prefers_relevant_multi_article_cluster():
    clusters = [
        {
            "id": 1,
            "title": "中国女足比赛",
            "member_count": 5,
            "keywords": ["女足", "比赛"],
        },
        {
            "id": 2,
            "title": "电影功夫女足定档",
            "member_count": 4,
            "keywords": ["功夫女足", "电影", "定档"],
        },
    ]
    assert choose_relevant_cluster(clusters, "《功夫女足》电影")["id"] == 2


def test_quality_gate_rejects_mock_and_invalid_frontend_values():
    detail = {
        "title": "功夫女足",
        "articles": {"total": 3, "articles": []},
        "sentiment_positive": 0.5,
        "sentiment_negative": 0.3,
        "sentiment_neutral": 0.2,
        "trend": {"dates": ["07-13"], "counts": [3]},
        "platform": {"platforms": [{"platform": "百度", "count": 3}]},
        "keywords": {"keywords": [{"word": "功夫女足", "source": "query"}]},
    }
    result = assess_frontend_data_quality(
        detail,
        propagation={"coverage_status": "insufficient", "limitations": ["no edges"]},
        dom_text="虚假风险 45 持续时间 45",
    )
    assert result["passed"] is False
    assert "FIXED_RISK_PLACEHOLDER" in result["failed_rules"]


def test_artifact_sanitizer_removes_token_and_credentials():
    value = {"token": "jwt-value", "safe": "Bearer jwt-value"}
    serialized = json.dumps(safe_artifact(value, ["jwt-value"]), ensure_ascii=False)
    assert "jwt-value" not in serialized
    assert "Bearer" not in serialized
    assert "token" not in serialized.lower()
```

- [x] **Step 2: Run RED**

```powershell
python -m pytest tests/test_run_keyword_e2e.py -q
```

Expected: module import failure.

- [x] **Step 3: Implement sanitization and cluster selection**

`safe_artifact()` must reuse recursive secret removal from `validate_backend_live.py`, and additionally remove JWT/token/password fields.

`choose_relevant_cluster()` must score:

- exact normalized phrase “功夫女足”: +10;
- both “功夫/女足” and “电影/影片/定档/上映”: +6;
- each query token overlap: +2;
- member count: capped at +5;
- generic football-only cluster without film evidence: -6;
- unrelated old “功夫足球” title: -4.

Return `None` when best score is below 6.

- [x] **Step 4: Implement frontend quality rules**

`assess_frontend_data_quality(detail, propagation, dom_text)` returns:

```python
{
    "passed": bool,
    "passed_rules": [],
    "failed_rules": [],
    "metrics": {},
    "warnings": [],
}
```

Rules cover title relevance, article count, article relevance ratio, platform count, finite heat, sentiment sum, trend alignment, platform-count alignment, keyword diversity, risk semantics, propagation limitations, fixed risk placeholders, DOM undefined/NaN/object text and required sections.

- [x] **Step 5: Run focused tests**

```powershell
python -m pytest tests/test_run_keyword_e2e.py -q
```

- [x] **Step 6: Commit**

```powershell
git add tools/run_keyword_e2e.py tests/test_run_keyword_e2e.py
git commit -m "test: add keyword end-to-end quality driver" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2: Implement isolated server, API and database orchestration

**Files:**
- Modify: `tools/run_keyword_e2e.py`
- Modify: `tests/test_run_keyword_e2e.py`

- [x] **Step 1: Write failing process and payload tests**

Test that the child environment:

- uses the dedicated absolute SQLite path;
- disables startup recovery;
- keeps asynchronous tasks enabled;
- disables Flask reloader;
- never serializes demo password or JWT.

Test API request payload exactly:

```json
{
  "keyword": "《功夫女足》电影",
  "platforms": ["baidu", "weibo", "zhihu", "bilibili"],
  "target_count": 24
}
```

- [x] **Step 2: Implement process lifecycle**

Implement:

- free-port check for 5000/8848;
- hidden backend process;
- HTTP health wait with deadline;
- hidden frontend process;
- graceful terminate then forced kill fallback;
- UTF-8 backend/frontend log files;
- `try/finally` cleanup.

Backend command:

```powershell
python -c "from app import create_app; app=create_app(); app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)"
```

- [x] **Step 3: Implement authenticated API flow**

1. Login with configured demo admin.
2. Save only user id/username/role.
3. Submit keyword search.
4. Poll `/api/tasks/{id}` every second and append status/progress/message summaries.
5. Fail only after explicit task failure or 15-minute deadline.
6. Read `analysis_run_id`, `aggregation_run_id`, `sentiment_run_id`.
7. Read aggregation clusters and choose the relevant cluster.
8. Publish cluster.
9. Save `event_id`.
10. Query events list, event detail, propagation, report, HTML export summary and one QA response.

QA question:

```text
请根据当前报道说明《功夫女足》电影的核心信息、舆论情绪和数据局限，并区分事实与推断。
```

- [x] **Step 4: Export intermediate database state**

Using the same SQLite URI with recovery disabled, export:

- Article and ArticleSnapshot;
- preprocessing fields and warnings;
- DocumentFeatures and embedding metadata;
- AnalysisRun and AnalysisRunArticle;
- AggregationRun, clusters and assignments;
- SentimentRun and article/event sentiment snapshots;
- Event, heat snapshots, lifecycle and metadata;
- Report and Task final record.

Raw and clean text are capped at 800 characters, with full length and SHA-256.

- [x] **Step 5: Run tests and commit**

```powershell
python -m pytest tests/test_run_keyword_e2e.py -q
git add tools/run_keyword_e2e.py tests/test_run_keyword_e2e.py
git commit -m "feat: orchestrate isolated keyword analysis cycle" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 3: Establish the real frontend runtime

**Files:**
- Verify: `frontend/package.json`
- Verify or update only when required: `frontend/package-lock.json`

- [ ] **Step 1: Install declared dependencies**

```powershell
cd frontend
npm install
```

Do not update package versions unless installation proves the lock file is inconsistent.

- [ ] **Step 2: Run production build**

```powershell
npm run build
```

Record Node/npm versions, exit status and warnings.

- [ ] **Step 3: Diagnose build failures systematically**

For each failure:

1. capture full error;
2. locate the exact source/import;
3. write or run the smallest available type/build check;
4. make the minimum change;
5. rerun build.

- [ ] **Step 4: Commit only demonstrated frontend fixes**

Do not commit `node_modules`. Commit lock/source changes only when required by successful build.

### Task 4: Run the real backend cycle and save API artifacts

**Files:**
- Create at runtime: `artifacts/kung_fu_women_football/`
- Keep sanitized results under: `tests/e2e/kung_fu_women_football/`

- [ ] **Step 1: Run the E2E API phase**

```powershell
python tools/run_keyword_e2e.py `
  --keyword "《功夫女足》电影" `
  --platform baidu `
  --platform weibo `
  --platform zhihu `
  --platform bilibili `
  --target-count 24 `
  --artifact-dir tests/e2e/kung_fu_women_football
```

- [ ] **Step 2: Inspect crawl quality**

Compute:

- documents per platform;
- valid/failed preprocessing;
- duplicates;
- title/content keyword relevance;
- empty/very-short content;
- publication-time coverage;
- interaction-field coverage.

If fewer than 3 relevant non-duplicate articles exist, retry once with target count 40 and record both attempts.

- [ ] **Step 3: Inspect aggregation before publishing**

Export every cluster and article membership. Publish only when the selected cluster score is at least 6 and manual inspection confirms the cluster is about the movie.

- [ ] **Step 4: Inspect post-publication outputs**

Verify Event title/summary, metadata evidence, sentiment snapshot, heat snapshot, lifecycle status, risk, keywords, report and propagation.

- [ ] **Step 5: Scan artifacts for secrets**

Configured-secret hits and JWT/password/header markers must all be zero.

### Task 5: Run the real Vue pages with Selenium

**Files:**
- Modify: `tools/run_keyword_e2e.py`
- Create runtime screenshots and DOM in the artifact directory

- [ ] **Step 1: Write browser-helper tests**

Test pure DOM checks and screenshot filename generation. Verify Chinese keyword and event id produce filesystem-safe names.

- [ ] **Step 2: Implement browser phase**

Use:

```text
C:\Program Files\Google\Chrome\Application\chrome.exe
```

Selenium options:

- headless new mode;
- 1440 × 1200 viewport;
- isolated temporary Chrome profile;
- browser console logging;
- no saved credentials.

Login through the real `/login` form. Navigate to `/analysis`, enter the keyword and confirm cached/completed state; navigate to dashboard, filter the event; then open `/events/{event_id}`.

- [ ] **Step 3: Capture user-visible evidence**

Save:

- analysis completion screenshot;
- dashboard screenshot;
- event detail full-page screenshot;
- final DOM;
- browser console messages;
- visible section names and values.

- [ ] **Step 4: Run quality gate**

Compare DOM-visible title, article count, sentiment, lifecycle and risk with API data. Fail on mock fixed 45, undefined, NaN, blank required sections or wrong event.

### Task 6: Repair demonstrated backend/frontend data-quality defects

**Files:**
- Modify only files proven defective by Tasks 4–5
- Add focused backend or frontend tests

- [ ] **Step 1: Classify every failure**

Categories:

- external source limitation;
- crawler mapping;
- preprocessing/analysis;
- aggregation selection;
- event postprocessing;
- API contract;
- frontend unwrap/field mapping;
- frontend mock or misleading fallback;
- browser timing/rendering.

- [ ] **Step 2: Fix code defects with TDD**

Likely high-risk checks:

- risk radar fixed values;
- keyword/source field mismatch;
- event search filter not reflected on dashboard;
- cached analysis UI lacking a direct result id;
- sparse trend or propagation empty-state handling;
- API client double-unwrapping assumptions.

Do not change behavior without a failing test or reproducible build/browser assertion.

- [ ] **Step 3: Re-run affected stages**

Reuse the same isolated database when safe; otherwise start a new attempt directory and preserve both before/after evidence.

### Task 7: Publish the user-quality report

**Files:**
- Create: `docs/功夫女足电影全链路实跑与前端数据质量报告.md`
- Modify: `docs/integration_report.md`
- Modify: `docs/frontend_changelog_and_memory.md` only when frontend code changes
- Modify: this plan

- [ ] **Step 1: Write the stage ledger**

For every stage record:

- inputs;
- outputs/counts;
- identifiers;
- status/warnings;
- artifact file;
- user-visible impact.

- [ ] **Step 2: Write user-perspective assessment**

Cover:

- relevance;
- completeness;
- consistency;
- readability;
- explainability;
- freshness;
- limitations;
- whether each chart/card helps or misleads.

- [ ] **Step 3: Record fixes and residual limitations**

Separate code defects from external data limitations. Include before/after screenshots when code changes.

- [ ] **Step 4: Commit report and safe artifacts**

Do not commit the SQLite runtime database, server logs containing headers, browser profile, `node_modules`, JWT or credentials.

### Task 8: Final verification

- [ ] **Step 1: Frontend build**

```powershell
cd frontend
npm run build
```

- [ ] **Step 2: E2E focused tests**

```powershell
python -m pytest tests/test_run_keyword_e2e.py tests/test_validate_backend_live.py -q
```

- [ ] **Step 3: Backend/full regression**

```powershell
python -m pytest backend/tests tests -q
```

- [ ] **Step 4: Secret and repository checks**

Confirm:

- no configured secret, JWT, password or authentication header in artifacts;
- `backend/.env` remains untracked;
- development SQLite unchanged;
- runtime DB/log/profile excluded;
- Git worktree contains only intended committed files.

- [ ] **Step 5: Final handoff**

Report exact crawl counts, selected cluster/event id, API quality results, browser evidence, fixes, remaining external/scientific limits and artifact/document paths.
