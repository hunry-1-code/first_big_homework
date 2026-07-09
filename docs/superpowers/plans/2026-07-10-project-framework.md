# Project Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable project skeleton for the public-opinion analysis system so teammates can later implement crawler, cleaning, NLP, LLM, reporting, and frontend modules independently.

**Architecture:** Flask exposes authenticated REST APIs and delegates long-running work to service/task abstractions. Vue provides the five required screens and connects to the backend API through a single client layer. Database models, service functions, and task records are defined now; complex algorithms remain stubbed with stable interfaces.

**Tech Stack:** Flask 3, SQLAlchemy 2, Flask-CORS, JWT, APScheduler placeholders, Vue 3, Vite, Pinia, Vue Router, Element Plus, ECharts placeholders.

---

### Task 1: Backend Skeleton

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/extensions.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/security.py`
- Create: `backend/app/core/response.py`
- Create: `backend/app/models/*.py`
- Create: `backend/app/api/*.py`
- Create: `backend/app/services/*.py`
- Create: `backend/app/tasks/*.py`
- Create: `backend/run.py`
- Create: `backend/requirements.txt`

- [ ] Build a Flask app factory with CORS, SQLAlchemy, and blueprint registration.
- [ ] Define stable SQLAlchemy models matching the confirmed requirement document.
- [ ] Add auth/admin decorators and JWT 24-hour login behavior.
- [ ] Add API placeholders for auth, events, QA, user center, crawler, import, tasks, and reports.
- [ ] Add service-layer stubs so each future module has a clear implementation boundary.

### Task 2: Frontend Skeleton

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.js`
- Create: `frontend/src/main.js`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/router/index.js`
- Create: `frontend/src/api/*.js`
- Create: `frontend/src/stores/*.js`
- Create: `frontend/src/views/*.vue`
- Create: `frontend/src/components/*.vue`

- [ ] Build a Vue 3 app with login, dashboard, event detail, QA, and personal center routes.
- [ ] Add route guards using the auth store and 24-hour JWT token.
- [ ] Add API modules that match backend skeleton endpoints.
- [ ] Add layout/navigation and placeholder views that future teammates can fill in.

### Task 3: Samples And Documentation

**Files:**
- Create: `data/samples/opinion_events.sample.json`
- Create: `docs/framework_overview.md`
- Modify: `README.md`

- [ ] Add JSON sample data matching the import API contract.
- [ ] Document backend/frontend startup commands and module ownership boundaries.
- [ ] Document where future teams should implement crawler, cleaning, LLM, report, and frontend logic.

### Task 4: Verification

**Files:**
- Create: `backend/tests/test_contracts.py`

- [ ] Add lightweight contract tests for pure service helpers where possible.
- [ ] Run Python syntax compilation over backend.
- [ ] If dependencies are installed, run Flask contract tests.
- [ ] Report exactly which verification commands passed and which were skipped due missing dependencies.
