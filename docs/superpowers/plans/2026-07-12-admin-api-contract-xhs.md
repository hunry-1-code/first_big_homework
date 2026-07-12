# Admin API, Response Contract And Xiaohongshu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement secure administrator user CRUD APIs, align event API responses with the required frontend contract, and repair Xiaohongshu live search using TikHub's official specification.

**Architecture:** Preserve existing internal model and analysis values, adding explicit serializers at the API service boundary. Add an isolated admin blueprint/service and an idempotent user-status migration. Extend the existing TikHub adapter without changing other platform contracts.

**Tech Stack:** Flask 3, Flask-SQLAlchemy, PyJWT, pytest, SQLite/MySQL migrations, requests, TikHub OpenAPI.

---

## File Map

- Modify `backend/app/models/user.py`: add status.
- Create `backend/app/services/admin_service.py`: user validation and CRUD.
- Create `backend/app/api/admin.py`: `/api/admin` endpoints.
- Modify `backend/app/api/__init__.py`: register admin blueprint.
- Modify `backend/app/api/auth.py` and `backend/app/core/security.py`: account status and fresh database identity.
- Create `backend/migrations/20260712_user_management.sql` and `backend/migrations/migrate_user_management.py`.
- Create `backend/tests/test_admin_users.py` and `backend/tests/test_user_management_migration.py`.
- Create `backend/app/services/api_contract_service.py`: platform, lifecycle, sentiment, heat and date serializers.
- Modify `backend/app/services/event_service.py`: stable list/detail contract.
- Modify `backend/tests/test_contracts.py` and `backend/tests/test_event_similarity_service.py`.
- Modify `backend/app/crawler/tikhub.py`: official Xiaohongshu parameters and cursor metadata.
- Modify `tools/validate_live_crawlers.py`: Unicode-safe keywords.
- Modify `backend/tests/test_crawler_adapters.py` and `tests/test_validate_live_crawlers.py`.

### Task 1: User Status Model And Migration

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/migrations/20260712_user_management.sql`
- Create: `backend/migrations/migrate_user_management.py`
- Create: `backend/tests/test_user_management_migration.py`

- [ ] Write migration tests proving a legacy user table gains `status`, existing rows become 1, and a second run is harmless.
- [ ] Run `python -m pytest -q backend/tests/test_user_management_migration.py` and verify RED because migration files are absent.
- [ ] Add `status = db.Column(db.Integer, nullable=False, default=1, server_default="1")` to `User`.
- [ ] Implement a dialect-aware Python migrator using SQLAlchemy inspection; SQLite executes `ALTER TABLE user ADD COLUMN status INTEGER NOT NULL DEFAULT 1`, MySQL executes the equivalent `TINYINT` statement only when absent.
- [ ] Run migration tests and `backend/tests/test_migration.py`; expect PASS.

### Task 2: Administrator User CRUD

**Files:**
- Create: `backend/app/services/admin_service.py`
- Create: `backend/app/api/admin.py`
- Modify: `backend/app/api/__init__.py`
- Create: `backend/tests/test_admin_users.py`

- [ ] Write failing API tests for admin permission, pagination/filtering, create, duplicate username, edit, password reset, role list, self-delete protection and last-admin protection.
- [ ] Verify RED with `python -m pytest -q backend/tests/test_admin_users.py`.
- [ ] Implement username regex `^[A-Za-z0-9_-]{3,50}$`, password length 6-128, roles `admin/user`, status `0/1`, and ISO datetime serialization.
- [ ] Implement list/create/update/reset/delete service functions. Count enabled administrators before role downgrade, disable or deletion; raise domain errors mapped to 400/404/409.
- [ ] Implement endpoints:

```text
GET    /api/admin/users
POST   /api/admin/users
PUT    /api/admin/users/<id>
PUT    /api/admin/users/<id>/password
DELETE /api/admin/users/<id>
GET    /api/admin/roles
```

- [ ] Register the blueprint at `/api/admin` and run the focused tests until GREEN.

### Task 3: Authentication Status Enforcement

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/core/security.py`
- Modify: `backend/tests/test_admin_users.py`
- Modify: existing auth tests if present.

- [ ] Add failing tests proving disabled users cannot log in, disabled users with an old JWT cannot access protected APIs, login updates `last_login_at`, and `/auth/me` returns fresh role/status.
- [ ] Run focused tests and verify RED.
- [ ] Reuse the existing PBKDF2 helpers for admin-created/reset passwords; do not introduce a second password format.
- [ ] In login, reject status 0 with HTTP 403 and update `last_login_at` on success.
- [ ] In `login_required`, load the user row by token subject/id, reject missing/disabled accounts, and populate `g.current_user` from current database fields.
- [ ] Run auth/admin tests and verify GREEN.

### Task 4: Event API Contract Serializer

**Files:**
- Create: `backend/app/services/api_contract_service.py`
- Modify: `backend/app/services/event_service.py`
- Modify: `backend/tests/test_contracts.py`
- Modify: `backend/tests/test_event_similarity_service.py`

- [ ] Add failing pure serializer tests for platform mapping, lifecycle mapping, sentiment normalization, Chinese sentiment labels, heat clamping, short dates and key points.
- [ ] Add failing event API/service tests asserting stable list/detail fields and exact seven-platform names.
- [ ] Implement pure helpers:

```python
api_platform_name(code: str) -> str | None
api_lifecycle_stage(stage: str) -> str
normalized_sentiment(positive, negative, neutral) -> tuple[float, float, float]
api_sentiment_label(value: str | None) -> str
clamp_ratio(value) -> float
clamp_heat(value) -> float
short_date(value: datetime | date | str) -> str
trend_key_points(dates: list[str], counts: list[int]) -> list[dict]
```

- [ ] Update event list serialization to clamp heat, normalize sentiment, map lifecycle and preserve pagination.
- [ ] Update event detail serialization so `report`, `trend`, `platform`, `keywords`, and `articles` always exist. Map article platform/label, clamp suspicious score, format publish time, and return `is_suspicious` as bool.
- [ ] Keep actual trend data only, maximum 14 points, with deduplicated first/peak/latest key points.
- [ ] Run contract and event tests until GREEN.

### Task 5: TikHub Xiaohongshu Official Contract

**Files:**
- Modify: `backend/app/crawler/tikhub.py`
- Modify: `backend/tests/test_crawler_adapters.py`
- Modify: `tools/validate_live_crawlers.py`
- Modify: `tests/test_validate_live_crawlers.py`

- [ ] Add failing adapter tests asserting request parameters include `sort_type=general`, `note_type=不限`, `time_filter=不限`, `source=explore_feed`, `ai_mode=0`, plus optional cursor values from `CrawlRequest.extra`.
- [ ] Add failing tests for `note_card` mapping, placeholder filtering and capture of response `search_id/search_session_id` in each document's `raw_json` metadata.
- [ ] Add a validator test using Unicode escapes for `人工智能` and asserting no `?` characters are sent.
- [ ] Run focused tests and verify RED.
- [ ] Implement official parameters and preserve response cursor metadata without logging credentials.
- [ ] Set validator default keyword from Unicode escapes and add a keyword-integrity check that returns `CODE_ERROR` when a Chinese test keyword becomes question marks.
- [ ] Run adapter/validator tests until GREEN.

### Task 6: Full Verification And Live Xiaohongshu Check

**Files:**
- Review: all modified files
- Output: `crawl_live_validation_results_xiaohongshu_fixed.json`

- [ ] Run `python -m pytest -q backend/tests tests`; expect zero failures.
- [ ] Run `python -m compileall -q backend tools tests`; expect exit 0.
- [ ] Run the user-status migration twice against a temporary SQLite database; expect both runs to succeed.
- [ ] Execute one low-volume Xiaohongshu request using a Unicode-safe keyword and the dedicated key.
- [ ] If valid notes return, verify one document passes preprocessing. If the official endpoint returns a genuine empty list, record `EMPTY_SUCCESS` with the exact sanitized request parameters and do not fabricate data.
- [ ] Scan generated results for `Authorization`, `Bearer`, API keys and password hashes; expect no matches.
- [ ] Run `git diff --check` and review all changed files before commit and merge.

