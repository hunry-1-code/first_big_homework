# Event Comment LLM Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make comments from every supported platform enter formal-event public-opinion analysis, with DeepSeek batch sentiment as the primary result and SnowNLP as an explicit fallback.

**Architecture:** Keep comment ingestion lightweight and separate from article clustering. Add a focused event-comment analysis orchestration service that upgrades all comments attached through `Article.event_id`, records LLM/fallback provenance, and refreshes cached opinion themes and narrative-gap analysis after event publication or an explicit historical backfill.

**Tech Stack:** Flask, SQLAlchemy, pytest, existing DeepSeek-compatible `LLMClient`, SnowNLP fallback.

---

### Task 1: Make batch sentiment provenance complete and deterministic

**Files:**
- Modify: `backend/app/analysis/sentiment_analyzer.py`
- Test: `backend/tests/test_comment_sentiment_batch.py`

- [ ] **Step 1: Write failing tests**

Add tests proving that a valid DeepSeek JSON response produces `method="llm_batch"` for every returned comment, while a client exception produces `method="snownlp_fallback"` rather than silently dropping results.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_comment_sentiment_batch.py`

Expected: failure because incomplete or invalid LLM rows are not currently normalized and fallback provenance is not guaranteed for every input.

- [ ] **Step 3: Implement minimal normalization**

Validate labels against `positive/neutral/negative`; after each batch, fill every missing input ID with a SnowNLP fallback result. Preserve `llm_batch` only for valid DeepSeek rows.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/test_comment_sentiment_batch.py`

Expected: all tests pass.

### Task 2: Upgrade an event's comments with DeepSeek-first semantics

**Files:**
- Modify: `backend/app/services/public_opinion_service.py`
- Test: `backend/tests/test_comment_service.py`

- [ ] **Step 1: Write failing tests**

Cover these cases:

- comments from B站 and news articles sharing one event are both selected;
- `llm_batch` overwrites the temporary label and stores `analysis_status="llm"`;
- `snownlp_fallback` stores `analysis_status="snownlp_fallback"` and retains a usable result;
- already-LLM comments are skipped on rerun;
- the function returns structured counts for selected, LLM-upgraded, fallback and failed comments.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pytest -q tests/test_comment_service.py`

Expected: failure because the current function returns only an integer and does not persist fallback provenance.

- [ ] **Step 3: Implement event-level upgrade result**

Change `upgrade_comment_sentiments(event_id)` to query all comments through articles whose `event_id` matches, call `analyze_comments_batch`, persist each result according to its method, commit once per event, and return a dictionary such as:

```python
{
    "selected": 15,
    "llm": 12,
    "snownlp_fallback": 3,
    "failed": 0,
}
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/test_comment_service.py`

Expected: all tests pass.

### Task 3: Orchestrate event comment analysis and refresh derived opinion data

**Files:**
- Create: `backend/app/services/event_comment_analysis_service.py`
- Modify: `backend/app/services/public_opinion_service.py`
- Test: `backend/tests/test_event_comment_analysis_service.py`

- [ ] **Step 1: Write failing orchestration tests**

Test that `analyze_event_comments(event_id)` performs sentiment upgrade first, then extracts themes and narrative gap, stores both in `Event.metadata_evidence`, and returns non-sensitive warnings if either optional LLM derivative fails.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_event_comment_analysis_service.py`

Expected: import failure because the orchestration service does not exist.

- [ ] **Step 3: Implement the focused service**

Expose one idempotent function:

```python
def analyze_event_comments(event_id: int) -> dict:
    ...
```

It must not create events, alter article membership, or add comments to article analysis runs.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/test_event_comment_analysis_service.py`

Expected: all tests pass.

### Task 4: Trigger comment analysis after formal event publication

**Files:**
- Modify: `backend/app/services/event_aggregation_service.py`
- Modify: `backend/app/tasks/jobs.py`
- Test: `backend/tests/test_event_aggregation_service.py`
- Test: `backend/tests/test_jobs.py`

- [ ] **Step 1: Write failing publication tests**

Verify `_postprocess_published_event` invokes event comment analysis after article membership is committed and exposes a `comments` status/count block. Verify the search pipeline no longer contains a second duplicate comment-analysis loop.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest -q tests/test_event_aggregation_service.py tests/test_jobs.py`

Expected: failure because comment analysis currently lives only in `run_search_analysis_pipeline` and returns no structured postprocess status.

- [ ] **Step 3: Move the trigger to publication postprocessing**

Call `analyze_event_comments(event_id)` inside `_postprocess_published_event`. Remove the duplicate best-effort loop from `run_search_analysis_pipeline`; retain task-stage reporting using the structured postprocess result where available.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `pytest -q tests/test_event_aggregation_service.py tests/test_jobs.py`

Expected: all tests pass.

### Task 5: Add a safe historical backfill command

**Files:**
- Create: `backend/scripts/backfill_event_comment_analysis.py`
- Test: `backend/tests/test_event_comment_analysis_service.py`

- [ ] **Step 1: Write a failing backfill test**

Test dry-run event selection, a single-event execution, and skipping events without comments. Ensure no API key or raw response is printed.

- [ ] **Step 2: Run test and verify RED**

Run: `pytest -q tests/test_event_comment_analysis_service.py`

Expected: failure because the command does not exist.

- [ ] **Step 3: Implement CLI arguments**

Support:

```text
--event-id ID
--all
--dry-run
```

Print only event IDs and aggregate result counts.

- [ ] **Step 4: Run test and verify GREEN**

Run: `pytest -q tests/test_event_comment_analysis_service.py`

Expected: all tests pass.

### Task 6: Verify the complete behavior and run the existing-data backfill

**Files:**
- Modify: `docs/verification/2026-07-15-system-improvement-final-report.md`
- Create: `docs/verification/2026-07-15-event-comment-llm-live-check.md`

- [ ] **Step 1: Run focused tests**

Run:

```powershell
cd backend
pytest -q tests/test_comment_sentiment_batch.py tests/test_comment_service.py tests/test_event_comment_analysis_service.py tests/test_event_aggregation_service.py tests/test_jobs.py
```

- [ ] **Step 2: Run the complete backend suite**

Run: `pytest -q`

Expected: all tests pass.

- [ ] **Step 3: Run static compilation**

Run: `python -m compileall -q app scripts`

Expected: exit code 0.

- [ ] **Step 4: Backfill existing formal events**

First run:

```powershell
python scripts/backfill_event_comment_analysis.py --all --dry-run
```

Then run the real backfill only after confirming the selected event IDs:

```powershell
python scripts/backfill_event_comment_analysis.py --all
```

- [ ] **Step 5: Verify database and API evidence**

Record per-event comment counts, platform distribution, `llm` versus `snownlp_fallback` counts, public keywords, themes and narrative-gap output. Explicitly note B站 comments whose article has no `event_id`; they remain pending until that article is published into an event.

- [ ] **Step 6: Update verification reports**

Write the actual commands, inputs, outputs and non-sensitive failure summaries into the live-check report.
