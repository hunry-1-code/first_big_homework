# Final Validation and Algorithm Self-Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete secret-safe isolated live validation for daily Top10 and the configured LLM, restore the development database, and publish an evidence-graded scientific self-assessment of every backend algorithm module.

**Architecture:** Add one standalone validator that inherits crawler/LLM credentials from the application configuration while overriding database and background-service settings for a short-lived process. Keep live artifacts strictly sanitized, then produce an audit that separates engineering verification from empirical model-quality evidence.

**Tech Stack:** Python, Flask application factory, SQLAlchemy, temporary SQLite, requests-based OpenAI-compatible LLM client, pytest, Markdown.

---

### Task 1: Add isolated final live validator

**Files:**
- Create: `tools/validate_backend_live.py`
- Create: `tests/test_validate_backend_live.py`
- Reuse: `tools/validate_live_crawlers.py`

- [x] **Step 1: Write failing isolation and sanitization tests**

Create tests for these public helpers:

```python
from tools.validate_backend_live import (
    classify_external_error,
    make_isolated_config,
    parse_llm_probe,
    sanitize_result,
)


def test_isolated_config_disables_long_running_services(tmp_path):
    class Base:
        TASK_RECOVER_ON_STARTUP = True
        TASKS_RUN_SYNC = False
        BGE_ENABLED = True
        AUTO_CREATE_DB = False

    config = make_isolated_config(
        Base,
        f"sqlite:///{(tmp_path / 'validation.db').as_posix()}",
    )

    assert config.TASK_RECOVER_ON_STARTUP is False
    assert config.TASKS_RUN_SYNC is True
    assert config.BGE_ENABLED is False
    assert config.AUTO_CREATE_DB is True


def test_result_sanitization_removes_known_secret_and_bearer():
    value = {
        "message": "Authorization: Bearer real-secret",
        "nested": {"api_key": "real-secret"},
    }
    sanitized = sanitize_result(value, ["real-secret"])
    serialized = json.dumps(sanitized, ensure_ascii=False)
    assert "real-secret" not in serialized
    assert "Authorization" not in serialized
    assert "api_key" not in serialized


def test_llm_probe_accepts_only_exact_minimal_json():
    assert parse_llm_probe('{"status":"ok"}') is True
    assert parse_llm_probe('```json\n{"status":"ok"}\n```') is True
    assert parse_llm_probe('{"status":"maybe"}') is False
```

Also test classification for HTTP 401/403, HTTP 429, connection/timeout, invalid JSON and unknown internal exceptions.

- [x] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest tests/test_validate_backend_live.py -q
```

Expected: collection fails because `tools.validate_backend_live` does not exist.

- [x] **Step 3: Implement pure safety helpers**

Implement:

```python
SENSITIVE_KEY = re.compile(
    r"authorization|api[-_]?key|access[-_]?token|secret|cookie",
    re.IGNORECASE,
)


def make_isolated_config(base_config, database_uri: str):
    return type(
        "LiveValidationConfig",
        (base_config,),
        {
            "SQLALCHEMY_DATABASE_URI": database_uri,
            "AUTO_CREATE_DB": True,
            "TASK_RECOVER_ON_STARTUP": False,
            "TASKS_RUN_SYNC": True,
            "BGE_ENABLED": False,
        },
    )


def sanitize_result(value, secrets: list[str]):
    if isinstance(value, dict):
        return {
            str(key): sanitize_result(item, secrets)
            for key, item in value.items()
            if not SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_result(item, secrets) for item in value]
    if isinstance(value, str):
        text = value
        for secret in secrets:
            if secret:
                text = text.replace(secret, "[REDACTED]")
        text = re.sub(
            r"(?i)bearer\s+[a-z0-9._~+/=-]+",
            "[REDACTED]",
            text,
        )
        text = re.sub(
            r"(?i)\b(?:authorization|cookie)\s*[:=]\s*[^\s,;]+",
            "[REDACTED]",
            text,
        )
        return text[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


def parse_llm_probe(content: str) -> bool:
    text = str(content or "").strip()
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text) == {"status": "ok"}
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def classify_external_error(error: Exception) -> str:
    combined = f"{getattr(error, 'code', '')} {error}".upper()
    if any(token in combined for token in ("401", "403", "AUTH", "UNAUTHORIZED")):
        return "AUTH_ERROR"
    if any(token in combined for token in ("429", "QUOTA", "RATE LIMIT", "BALANCE")):
        return "QUOTA_ERROR"
    if any(token in combined for token in ("TIMEOUT", "CONNECTION", "DNS", "SSL", "NETWORK")):
        return "NETWORK_ERROR"
    if any(token in combined for token in ("JSON", "STRUCTURE", "FORMAT", "CONTENT IS EMPTY")):
        return "FORMAT_ERROR"
    return "INTERNAL_ERROR"
```

No helper may print configuration values or raw third-party response bodies.

- [x] **Step 4: Implement the isolated Top10 probe**

Implement `run_daily_hot_probe(config_class)`:

1. Build the Flask app with the isolated config.
2. Assert the effective app settings keep recovery disabled and use SQLite.
3. Call `collect_daily_hot()` with:

```python
sources=["weibo_hot", "baidu_hot", "zhihu_hot"]
source_limit=1
result_limit=1
rrf_k=60
ttl_seconds=0
force=True
```

4. Serialize one item.
5. Return only:

```python
{
    "status": run.status,
    "available_sources": run.available_sources or [],
    "failed_sources": run.failed_sources or [],
    "item_count": run.item_count,
    "returned_items": len(payload["items"]),
    "has_event_id_field": bool(payload["items"])
        and "event_id" in payload["items"][0],
    "scheduler_started": "task_recovery_scheduler" in app.extensions,
}
```

Do not enqueue item enrichment and do not include titles, URLs or raw source payloads in the artifact.

- [x] **Step 5: Implement the one-call LLM probe**

Instantiate `LLMClient` from the isolated app configuration. Send exactly one request:

```python
[
    {
        "role": "system",
        "content": "Return only compact JSON. Do not add Markdown.",
    },
    {
        "role": "user",
        "content": 'Return exactly {"status":"ok"}.',
    },
]
```

Use `temperature=0` and `max_tokens=30`. Return only status, model name and `content_valid`. On failure, return the fixed error classification and a sanitized fixed-length message.

- [x] **Step 6: Implement CLI and artifact safety gate**

CLI arguments:

```text
--env-file backend/.env
--output tests/final_backend_live_validation_results.json
--skip-top10
--skip-llm
```

Load the environment without printing it. Use `tempfile.TemporaryDirectory()` for SQLite. Before writing JSON:

1. sanitize the complete result;
2. serialize it;
3. verify no configured secret value remains;
4. verify case-insensitive `Authorization`, `Bearer` and `Cookie` do not remain;
5. write UTF-8 JSON only if the scan passes.

Exit non-zero only for `INTERNAL_ERROR`, `FORMAT_ERROR`, failed secret scan or invalid isolated runtime state. Authentication, quota and network failures remain documented external outcomes.

- [x] **Step 7: Run focused tests and commit**

Run:

```powershell
python -m pytest tests/test_validate_backend_live.py tests/test_validate_live_crawlers.py -q
```

Expected: all tests pass.

Commit:

```powershell
git add tools/validate_backend_live.py tests/test_validate_backend_live.py
git commit -m "test: add isolated backend live validator" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2: Run live probes without database pollution

**Files:**
- Keep: `tests/daily_hot_live_validation_results.json`
- Create: `tests/final_backend_live_validation_results.json`
- Restore: `backend/instance/opinion_analysis_dev.db`

- [x] **Step 1: Confirm no backend Python process is running**

Run:

```powershell
Get-Process python -ErrorAction SilentlyContinue |
  Select-Object Id,ProcessName,StartTime,Path
```

If a user-started backend process exists, do not stop it. Delay database restoration until it exits. If no process exists, continue.

- [x] **Step 2: Restore only the database modification produced by the earlier probe**

Verify that the database is the only tracked non-document change, then run:

```powershell
git restore --source=HEAD -- backend/instance/opinion_analysis_dev.db
git status --short
```

The live result JSON files must remain untracked or modified; the development database must be clean.

- [x] **Step 3: Run the isolated combined probe**

Run:

```powershell
python tools/validate_backend_live.py `
  --env-file backend/.env `
  --output tests/final_backend_live_validation_results.json
```

Expected runtime properties:

- process exits without APScheduler shutdown errors;
- no SQLite lock warnings;
- no BGE or Hugging Face model download;
- Top10 uses three sources with limit 1;
- LLM makes one request.

- [x] **Step 4: Scan artifacts without displaying secrets**

Run an in-memory Python scan that loads `Config` and checks configured secret values against:

```text
tests/daily_hot_live_validation_results.json
tests/final_backend_live_validation_results.json
docs/integration_report.md
docs/后端系统现状与接口说明.md
```

The command may print file names and hit counts only. It must never print the matching secret.

Also run:

```powershell
rg -n -i "authorization|bearer|cookie|api[_-]?key|access[_-]?token" `
  tests/daily_hot_live_validation_results.json `
  tests/final_backend_live_validation_results.json
```

Expected: no matches.

- [x] **Step 5: Commit safe live artifacts**

Inspect both JSON files. Commit only after the secret scans pass:

```powershell
git add tests/daily_hot_live_validation_results.json tests/final_backend_live_validation_results.json
git commit -m "test: record low-volume backend live validation" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 3: Produce the algorithm scientific self-assessment

**Files:**
- Create: `docs/后端算法科学性合理性完整性自评.md`
- Reference: `docs/backend_algorithm_audit.md`
- Reference: `docs/integration_report.md`
- Reference: `docs/后端系统现状与接口说明.md`
- Reference: backend algorithm and service modules

- [ ] **Step 1: Build an evidence inventory**

For each of the 13 modules in the approved design, record:

- implementation files;
- algorithm or rule version;
- focused automated tests;
- integration tests;
- live validation evidence;
- presence or absence of labeled-data metrics;
- known domain assumptions.

Use `rg` to locate configuration parameters, warnings, versions and test cases. Do not infer empirical accuracy from test count.

- [ ] **Step 2: Write the score matrix**

Create a matrix with columns:

```text
模块 | 科学性(1-5) | 合理性(1-5) | 完整性(1-5) |
证据等级(E0-E5) | 当前结论 | 首要缺口
```

Scoring rules:

- 5 requires strong theoretical fit plus E4/E5 evidence;
- 4 allows sound methods and complete engineering with missing large-scale validation;
- 3 means usable engineering with material empirical or domain limitations;
- 2 means heuristic-heavy or incomplete evidence chain;
- 1 means conceptually invalid or largely placeholder behavior.

No current module may receive evidence above E3 unless the repository contains a representative labeled evaluation or online experiment.

- [ ] **Step 3: Write per-module assessments**

Each module section must contain:

1. current implementation;
2. scientific basis;
3. what is reasonable for this project;
4. completeness and failure handling;
5. evidence actually available;
6. limitations;
7. concrete next experiment.

Explicitly state:

- crawler success does not prove stable long-term availability;
- TF-IDF/LDA/BGE parameters are not cross-domain calibrated;
- RRF is appropriate for rank fusion but title equivalence remains heuristic;
- LLM/SnowNLP sentiment lacks a representative labeled Chinese opinion dataset;
- heat is an explainable ranking score, not an objective social-impact measurement;
- lifecycle is a rule-based state estimator, not a learned forecast;
- risk output is suspiciousness assessment, not fact checking;
- propagation edges are evidence-weighted inferences, not verified repost links;
- LLM metadata, QA and report text can hallucinate and require evidence display.

- [ ] **Step 4: Add prioritized validation roadmap**

Define:

- **P0 engineering**: production monitoring, scheduler/process lifecycle, secret-safe observability;
- **P1 empirical**: labeled aggregation pairs, sentiment set, lifecycle sequences, propagation edges and risk cases;
- **P2 research**: cross-domain calibration, learning-to-rank heat, temporal graph inference and retrieval-grounded fact evidence.

For each proposed dataset, name the unit of annotation and metrics:

- aggregation: pair/cluster, precision/recall/F1, B-cubed or ARI;
- sentiment: article label/score, macro-F1, calibration error;
- lifecycle: event-day stage, macro-F1 and transition violation rate;
- risk: article evidence label, precision-recall and false-positive rate by domain;
- propagation: directed article pair, edge precision/recall;
- Top10: daily human relevance ordering, nDCG@10 and source coverage.

- [ ] **Step 5: Self-review the document**

Check:

- every approved module is present;
- every score has evidence and a limitation;
- no “accurate”, “proven” or “reliable” claim appears without E4/E5;
- no frontend-only concern is scored as a backend algorithm;
- no key, token, personal data or raw third-party payload appears.

### Task 4: Update final project records

**Files:**
- Modify: `docs/integration_report.md`
- Modify: `docs/后端系统现状与接口说明.md`
- Modify: `docs/superpowers/plans/2026-07-13-daily-top10-hotspots.md`
- Modify: `docs/superpowers/plans/2026-07-13-final-validation-and-algorithm-self-audit.md`

- [ ] **Step 1: Record exact automated results**

Record:

- Top10 focused suite count;
- full suite count;
- warning count and categories;
- compatibility contract result.

- [ ] **Step 2: Record live results conservatively**

Record each platform status, combined Top10 status, item count, LLM status/model and timestamp. External failures must retain their classification. Do not describe one successful call as permanent availability.

- [ ] **Step 3: Record the isolated-validation correction**

Document that the first direct service probe succeeded but incorrectly started the production recovery scheduler and modified the development SQLite file. State that the final validator uses a temporary database and disables long-running services, and that the tracked database was restored.

- [ ] **Step 4: Mark all plan checkboxes accurately**

Mark Daily Top10 Task 8 complete only after automated tests, live checks, secret scan and documentation are all finished.

- [ ] **Step 5: Commit audit and records**

```powershell
git add docs/后端算法科学性合理性完整性自评.md `
  docs/integration_report.md `
  docs/后端系统现状与接口说明.md `
  docs/superpowers/plans/2026-07-13-daily-top10-hotspots.md `
  docs/superpowers/plans/2026-07-13-final-validation-and-algorithm-self-audit.md
git commit -m "docs: publish final backend algorithm self-assessment" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 5: Final verification and delivery

**Files:**
- Verify all modified and created files

- [ ] **Step 1: Run validator unit tests**

```powershell
python -m pytest tests/test_validate_backend_live.py tests/test_validate_live_crawlers.py -q
```

- [ ] **Step 2: Run Top10 focused tests**

```powershell
python -m pytest backend/tests/test_daily_hot.py backend/tests/test_daily_hot_migration.py backend/tests/test_daily_hot_service.py backend/tests/test_daily_hot_api.py backend/tests/test_daily_hot_enrichment.py backend/tests/test_jobs.py backend/tests/test_hotspot_service.py -q
```

- [ ] **Step 3: Run the full suite**

```powershell
python -m pytest backend/tests tests -q
```

Expected: zero failures.

- [ ] **Step 4: Verify repository and secret state**

```powershell
git diff --check
git status --short
git log -8 --oneline
```

Confirm:

- `backend/.env` is not tracked;
- `backend/instance/opinion_analysis_dev.db` is unmodified;
- only intended artifacts and documents are committed;
- result JSON files contain no sensitive markers or configured secret values.

- [ ] **Step 5: Complete plan and report**

Mark this plan complete, commit any final checkbox-only update, and report:

- exact automated test evidence;
- exact live validation classifications;
- audit document path;
- remaining scientific limitations;
- latest commit and clean/dirty repository state.
