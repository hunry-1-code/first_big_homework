# Core Algorithm Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make clustering, propagation inference and lifecycle classification stable, conservative and backward-compatible.

**Architecture:** Keep pure algorithms independent of Flask and SQLAlchemy. Add structured result objects while preserving string-return compatibility wrappers used by existing callers. Persist results only from service/update workflows, never from read-only detail requests.

**Tech Stack:** Python dataclasses, deterministic numerical rules, Flask services, SQLAlchemy, pytest.

---

### Task 1: Correct cosine semantics and add soft time decay

**Files:**
- Modify: `backend/app/analysis/event_similarity.py`
- Modify: `backend/app/analysis/event_clusterer.py`
- Modify: `backend/tests/test_event_aggregation_algorithms.py`

- [x] **Step 1: Add failing cosine and time tests**

```python
from app.analysis.event_similarity import cosine_similarity

def test_orthogonal_and_negative_vectors_do_not_gain_similarity(self):
    self.assertEqual(cosine_similarity([1, 0], [0, 1]), 0.0)
    self.assertEqual(cosine_similarity([1, 0], [-1, 0]), 0.0)
```

Add a test calling `_time_compatibility` with a 60-day gap and a 30-day half-life; assert `0 < score < 0.5` instead of zero.

- [x] **Step 2: Run and verify RED**

```powershell
python -m pytest backend/tests/test_event_aggregation_algorithms.py -q
```

- [x] **Step 3: Implement corrected formulas**

```python
raw = dot / (left_norm * right_norm)
return _clamp(max(0.0, raw))
```

```python
gap_days = min_gap_seconds / 86400
half_life = max(1.0, float(config.maximum_event_gap_days))
return math.exp(-math.log(2.0) * gap_days / half_life)
```

- [x] **Step 4: Run tests and commit**

```powershell
python -m pytest backend/tests/test_event_aggregation_algorithms.py -q
git add backend/app/analysis/event_similarity.py backend/app/analysis/event_clusterer.py backend/tests/test_event_aggregation_algorithms.py
git commit -m "fix: 修正事件相似度与时间衰减" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2: Implement three-zone clustering and deterministic refinement

**Files:**
- Modify: `backend/app/analysis/event_clusterer.py`
- Modify: `backend/tests/test_event_aggregation_algorithms.py`

- [x] **Step 1: Add failing ambiguity and order-independence tests**

Create documents whose best score is between `create_threshold` and `attach_threshold`; assert they are reconsidered after later clusters exist. Add a shuffled-input test asserting the final `article_id -> cluster member ids` partition is identical across permutations.

Use this comparison helper in tests:

```python
def partition(result):
    return sorted(
        sorted(item.article_id for item in cluster.documents)
        for cluster in result.clusters
    )
```

- [x] **Step 2: Run and verify RED**

```powershell
python -m pytest backend/tests/test_event_aggregation_algorithms.py::EventClustererTest -q
```

- [x] **Step 3: Extract focused helpers**

Add:

```python
def _best_match(document, clusters, config): ...
def _create_cluster(document, clusters): ...
def _recompute_and_renumber(clusters, assignments): ...
def _refine_assignments(documents, clusters, assignments, config): ...
```

First-pass decisions:

```python
if best is None:
    create seed cluster
elif best.hard_conflict or best.final_score < config.create_threshold:
    create distinct cluster
elif best.final_score >= config.attach_threshold:
    attach
else:
    record action="ambiguous" with cluster_index=None
```

Refinement attaches ambiguous documents only above `attach_threshold`; clearly distinct documents create new clusters. Reassignment of existing members requires an improvement of at least `move_margin`.

- [x] **Step 4: Run algorithm and aggregation service tests**

```powershell
python -m pytest backend/tests/test_event_aggregation_algorithms.py backend/tests/test_event_aggregation_service.py -q
```

- [x] **Step 5: Commit**

```powershell
git add backend/app/analysis/event_clusterer.py backend/tests/test_event_aggregation_algorithms.py
git commit -m "feat: 增加事件聚类歧义区与二次重分配" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 3: Require real evidence for inferred propagation edges

**Files:**
- Modify: `backend/app/propagation/evidence.py`
- Modify: `backend/app/propagation/scorer.py`
- Modify: `backend/app/propagation/builder.py`
- Modify: `backend/tests/test_propagation.py`

- [x] **Step 1: Add failing evidence tests**

Keep the existing unrelated-articles regression. Add:

```python
def test_textual_weibo_repost_is_explicit_evidence(self):
    parent = self._article(1, "某公司发布公告", 0, author="账号甲")
    child = self._article(2, "转发公告", 1, content="//@账号甲 某公司发布公告")
    result = build_propagation_graph([parent, child])
    edge = result["graph"]["links"][0]
    self.assertEqual(edge["evidence_type"], "explicit")
```

Add a related follow-up case without explicit repost and assert it creates one inferred edge with component evidence.

- [x] **Step 2: Run and verify RED**

```powershell
python -m pytest backend/tests/test_propagation.py::PropagationBuilderTest -q
```

- [x] **Step 3: Separate scoring components**

Replace duplicated `shared=sim` with a structured scorer:

```python
@dataclass(frozen=True)
class InferredEvidence:
    semantic: float
    time: float
    source: float
    entity_or_keyword: float
    cross_platform: float
    final_score: float
    reasons: tuple[str, ...]
```

Require `semantic >= 0.20`, at least one supporting signal (`source` or `entity_or_keyword`), and `final_score >= 0.38`. Time and cross-platform status cannot create an edge by themselves.

- [x] **Step 4: Expand explicit parsing**

Parse structured parent IDs first, then `//@账号`, `转自账号`, `来源：账号` text. Match normalized author names in both containment directions while rejecting one-character names.

- [x] **Step 5: Build conservative edges**

Builder chooses at most one parent, prefers explicit evidence, includes component scores in `evidence`, and leaves unrelated nodes as independent roots.

- [x] **Step 6: Run tests and commit**

```powershell
python -m pytest backend/tests/test_propagation.py -q
git add backend/app/propagation backend/tests/test_propagation.py
git commit -m "fix: 提高传播路径推断证据门槛" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 4: Remove propagation dead code and expose coverage status

**Files:**
- Modify: `backend/app/services/event_service.py`
- Modify: `backend/tests/test_propagation.py`
- Modify or create: `backend/tests/test_event_api.py` if no existing event propagation API contract test exists.

- [x] **Step 1: Add a failing service/API shape test**

Assert propagation data contains:

```python
self.assertIn(data["coverage_status"], {"sufficient", "insufficient"})
self.assertEqual(data["graph_mode"], "propagation")
self.assertIsInstance(data["limitations"], list)
```

For unrelated articles assert `coverage_status == "insufficient"` and empty links.

- [x] **Step 2: Run and verify RED**

- [x] **Step 3: Delete the unreachable implementation after the early return**

Keep `build_propagation_graph()` as the only graph authority. Add coverage fields based on node/edge/evidence counts; do not force an origin edge.

- [x] **Step 4: Run propagation and event service/API tests**

```powershell
python -m pytest backend/tests/test_propagation.py backend/tests -q -k "event and propagation"
```

- [x] **Step 5: Commit**

Commit service and tests with a focused Chinese `fix:` message.

### Task 5: Add structured lifecycle analysis while preserving the four-stage wrapper

**Files:**
- Modify: `backend/app/analysis/trend_predictor.py`
- Modify: `backend/tests/test_trend_predictor.py`

- [ ] **Step 1: Correct stale enum tests and add structured-result tests**

Replace `衰退期` expectations with `消退期`. Add:

```python
prediction = analyze_lifecycle([1, 2, 3], previous_stage="潜伏期")
self.assertEqual(prediction.stage, "潜伏期")
self.assertEqual(prediction.status, "data_insufficient")
self.assertLess(prediction.confidence, 0.5)
```

Add monotonic tests ensuring a previous `高潮期` cannot silently return `成长期` and a previous `消退期` remains `消退期` unless an explicit reactivation flag is returned.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest backend/tests/test_trend_predictor.py -q
```

- [ ] **Step 3: Introduce a result dataclass**

```python
@dataclass(frozen=True)
class LifecyclePrediction:
    stage: str
    status: str
    confidence: float
    evidence: dict
    reactivated: bool = False
```

Implement `analyze_lifecycle(daily_counts, previous_stage=None)` using point count, normalized recent slope, peak ratio and sustained decline. Keep:

```python
def predict_lifecycle_stage(daily_counts):
    return analyze_lifecycle(daily_counts).stage
```

- [ ] **Step 4: Tune only against explicit cases**

Required outcomes:

- `[3,4,5,3,5]` → `潜伏期`.
- `[5,15,30,50,80,120]` → `成长期`.
- `[80,100,120,115,118,116,114]` → `高潮期`.
- sustained fall from peak → `消退期`.

- [ ] **Step 5: Run tests and commit**

```powershell
python -m pytest backend/tests/test_trend_predictor.py -q
git add backend/app/analysis/trend_predictor.py backend/tests/test_trend_predictor.py
git commit -m "feat: 增加可解释生命周期判定" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 6: Persist lifecycle results only during event updates

**Files:**
- Modify: `backend/app/models/event.py`
- Modify: `backend/app/services/event_aggregation_service.py`
- Modify: `backend/app/services/hotspot_service.py`
- Modify: `backend/app/services/event_service.py`
- Create: `backend/migrations/20260713_event_maturity.sql`
- Create: `backend/migrations/migrate_event_maturity.py`
- Test: `backend/tests/test_event_aggregation_service.py`
- Test: `backend/tests/test_hotspot_service.py`

- [ ] **Step 1: Add failing persistence/read-only tests**

Assert event update workflows save `lifecycle_status`, `lifecycle_confidence` and JSON evidence. Add a detail-read test that records `event.updated_at`, calls `get_event_detail()`, and asserts no lifecycle fields or timestamps were changed.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Add model fields and idempotent migration**

```python
lifecycle_status = db.Column(db.String(24), nullable=False, default="data_insufficient")
lifecycle_confidence = db.Column(db.Float, nullable=False, default=0.0)
lifecycle_evidence = db.Column(db.JSON)
lifecycle_updated_at = db.Column(db.DateTime)
```

- [ ] **Step 4: Add one event lifecycle update helper**

Create a focused service helper that receives an Event and daily counts, calls `analyze_lifecycle(previous_stage=event.lifecycle_stage)`, updates the four fields and commits only as part of the caller transaction.

- [ ] **Step 5: Make event detail serialization read-only**

Return lifecycle metadata without calling `db.session.commit()` or changing the Event.

- [ ] **Step 6: Run migration, service and full core tests**

```powershell
python -m pytest backend/tests/test_event_aggregation_service.py backend/tests/test_hotspot_service.py backend/tests/test_trend_predictor.py -q
```

- [ ] **Step 7: Commit**

Commit model, migration, services and tests together because they form one schema contract.
