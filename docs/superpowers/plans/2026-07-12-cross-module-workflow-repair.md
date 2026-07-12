# Cross-Module Workflow Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the search-cluster-to-formal-event workflow gaps and replace placeholder QA/report behavior.

**Architecture:** Add an idempotent post-publication orchestration service. Recompute formal event snapshots from cached article results, finalize existing hotspot topics, persist a usable report, and provide context-grounded LLM QA.

**Tech Stack:** Flask, SQLAlchemy, SQLite/MySQL-compatible models, requests-based OpenAI-compatible LLM client, unittest/pytest.

---

### Task 1: Publication-derived data orchestration

**Files:** `backend/app/services/event_aggregation_service.py`, `backend/app/services/event_postprocess_service.py`, `backend/tests/test_event_aggregation_service.py`

- [ ] Add a failing publication test asserting formal sentiment snapshot, event linkage, report overview and idempotency.
- [ ] Run the focused test and confirm the missing snapshot failure.
- [ ] Implement a post-publication orchestrator that commits publication first, runs global sentiment, finalizes matching hotspot heat, and persists report data.
- [ ] Return per-stage status/warnings from publication and make repeated publication call the repair path.
- [ ] Run focused aggregation, sentiment, hotspot and report tests.

### Task 2: Context-grounded LLM QA

**Files:** `backend/app/services/qa_service.py`, `backend/tests/test_qa.py`

- [ ] Add failing tests for event context in the prompt, LLM model/method metadata, missing event, and explicit fallback.
- [ ] Implement event context construction and call `LLMClient.chat` using configured API settings.
- [ ] Persist in-process history with method/model/warnings metadata and preserve current API shape.
- [ ] Run focused QA tests.

### Task 3: SQLite heartbeat contention

**Files:** `backend/app/tasks/runner.py`, `backend/tests/test_jobs.py`

- [ ] Add a failing test proving synchronous SQLite jobs do not start a competing heartbeat thread.
- [ ] Gate heartbeat creation for synchronous SQLite execution while retaining async heartbeat behavior.
- [ ] Run job/recovery tests.

### Task 4: Ordered workflow verification

**Files:** `backend/tests/test_system_workflow.py` (if a reusable fixture is needed)

- [ ] Add/extend a deterministic ordered integration test covering crawl through formal event downstream APIs.
- [ ] Run the complete backend suite.
- [ ] Execute at least three fresh real workflow runs against a temporary database and configured external APIs.
- [ ] Inspect warnings and repair any reproducible product defect before final verification.
