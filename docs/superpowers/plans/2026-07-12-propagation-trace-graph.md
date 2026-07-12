# Propagation Trace Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dense title-similarity graph with an evidence-based propagation forest and display it as an interactive ECharts graph plus phase timeline.

**Architecture:** Pure backend propagation modules build nodes, explicit/inferred edges, phases and summaries from event articles. The existing endpoint delegates to the builder. Vue components consume the stable graph contract and distinguish explicit and inferred relations visually.

**Tech Stack:** Python, Flask, SQLAlchemy, pytest, Vue 3, Element Plus, ECharts, Vite.

---

### Task 1: Propagation Result And Evidence Extraction

**Files:** Create `backend/app/propagation/result.py`, `evidence.py`, `__init__.py`; modify `backend/tests/test_propagation.py`.

- [ ] Add failing tests for explicit parent IDs, quoted/retweeted objects, source URLs and “据/转自/来源” text evidence.
- [ ] Run `python -m pytest -q backend/tests/test_propagation.py` and verify RED.
- [ ] Implement dataclasses and normalized evidence extraction without database dependencies.
- [ ] Re-run focused tests until GREEN.

### Task 2: Sparse Parent Scoring And Forest Builder

**Files:** Create `backend/app/propagation/scorer.py`, `builder.py`; modify `backend/tests/test_propagation.py`.

- [ ] Add failing tests for explicit-edge priority, one inferred parent, low-similarity disconnection, no cycles, no time reversal and multiple roots.
- [ ] Implement title/body token similarity, keyword overlap, time proximity, source-text evidence and cross-platform score.
- [ ] Build edges in chronological order; use threshold 0.55 and select one highest-scoring inferred parent.
- [ ] Preserve nodes with unreliable time but do not use them as confident roots.
- [ ] Run propagation tests until GREEN.

### Task 3: Key Nodes, Phases And Graph Pruning

**Files:** Create `backend/app/propagation/phases.py`; modify `builder.py` and tests.

- [ ] Add failing tests for origin candidates, platform-first nodes, influencers, media, official response, peak content and revival.
- [ ] Implement importance scoring and phase generation.
- [ ] Implement pruning that retains at most 40 nodes while preserving key nodes and their ancestor paths.
- [ ] Verify stable empty/single-node graphs.

### Task 4: API Integration

**Files:** Modify `backend/app/services/event_service.py`, `backend/tests/test_propagation.py`.

- [ ] Add an integration test that inserts Event/Article rows and calls `get_propagation_data`.
- [ ] Verify RED against the old response.
- [ ] Replace embedded graph logic with `build_propagation_graph`, mapping platform names through `api_contract_service`.
- [ ] Return summary, key_nodes, phases, graph.nodes, graph.links and graph.secondary_links.
- [ ] Run propagation and API tests until GREEN.

### Task 5: Vue Propagation UI

**Files:** Modify `frontend/src/api/events.js`, `frontend/src/views/DetailView.vue`, `frontend/src/styles.css`; create `frontend/src/components/PropagationGraph.vue`, `PropagationTimeline.vue`.

- [ ] Add `getEventPropagation(id)`.
- [ ] Add a propagation tab that loads the endpoint on detail-page mount.
- [ ] Implement ECharts graph with time-oriented node positions, category colors, solid explicit edges, dashed inferred edges, tooltips and resize cleanup.
- [ ] Implement key-phase timeline, coverage notice, loading/error/empty states and “展开普通节点” control.
- [ ] Run `npm run build`; expect exit 0.

### Task 6: Full Verification And Demonstration

**Files:** Review all changed files.

- [ ] Run `python -m pytest -q backend/tests tests`; expect zero failures.
- [ ] Run `python -m compileall -q backend tools tests`.
- [ ] Run `npm run build` in `frontend`.
- [ ] Seed or reuse a representative event dataset, start backend/frontend and capture the rendered propagation page for inspection.
- [ ] Check graph density, edge evidence, empty state and absence of secrets.
- [ ] Run `git diff --check`, commit, merge to main, verify again and clean the worktree.
