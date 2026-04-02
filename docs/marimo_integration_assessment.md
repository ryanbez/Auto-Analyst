# Marimo Integration Assessment for Auto-Analyst

## Goal
Evaluate whether this repository can be adapted for a **marimo app** workflow where end users can:
1. ask questions in chat,
2. generate and view plots,
3. get analytical/code responses,
4. run an autopilot flow when new data arrives,
5. automatically label new data.

---

## What already works well (from this repo)

### 1) Chat + multi-agent analysis ✅
- Backend already exposes chat endpoints for explicit agent routing (`/chat/{agent_name}`) and planner routing (`/chat`) with session/dataset context.
- The architecture is DSPy multi-agent, so adding new specialized agents is straightforward.

### 2) Plotting + analysis response ✅
- Code execution returns both Plotly and Matplotlib payloads.
- Frontend already renders Plotly with `react-plotly.js` and supports code execution loop from chat.

### 3) Good base for marimo integration ✅
- marimo can render Plotly/Matplotlib natively, so API adapter + UI glue is the main work.

---

## Missing pieces and practical fixes (implementable now)

Below is a **buildable** checklist (not just theory).

### A. Missing: Event-driven ingestion/autopilot trigger
**Current gap**
- No clear generalized trigger engine for “new data arrived → run analysis/labeling automatically”.

**Fix we can implement now**
1. Add a new endpoint: `POST /autopilot/ingest-event`
   - payload: `source_id`, `dataset_uri`, `schema_version`, `event_time`, `idempotency_key`
2. Persist event to DB table `autopilot_runs` with status lifecycle:
   - `queued -> running -> completed|failed|needs_review`
3. Add worker process (RQ/Celery/Arq/Temporal) to consume events and execute pipeline.
4. Add idempotency check on `idempotency_key` to avoid duplicate runs.

**Definition of Done**
- If same event arrives twice, second call returns existing run_id (no duplicate work).

---

### B. Missing: Data contract + schema drift guardrails
**Current gap**
- No explicit contract validation before analysis/labeling.

**Fix we can implement now**
1. Create `dataset_contracts` table:
   - `source_id`, expected columns, dtypes, target column, null thresholds.
2. Add validator step before running agents:
   - hard fail for missing required columns,
   - warning for extra columns or mild type drift.
3. Write drift signals into `autopilot_run_metrics`.

**Definition of Done**
- Every run stores `validation_status` and drift summary JSON.

---

### C. Missing: Production auto-label pipeline
**Current gap**
- Repo can generate ML code, but no complete auto-label service flow.

**Fix we can implement now**
1. Add `labeling_jobs` table + `label_predictions` table.
2. Implement label strategy (v1):
   - load latest approved model by `source_id` from model registry,
   - infer `predicted_label` + `confidence`,
   - auto-accept when `confidence >= threshold`,
   - route low-confidence rows to review queue.
3. Add `human_review_queue` table and `POST /labels/review` endpoint.
4. Add periodic retraining trigger (e.g., every N reviewed rows or weekly).

**Definition of Done**
- Pipeline produces traceable labels with `model_version`, `feature_hash`, and `decision_reason`.

---

### D. Missing: Reliability + reproducibility
**Current gap**
- Autopilot jobs need deterministic replay and observability.

**Fix we can implement now**
1. Store pipeline artifacts per run:
   - prompt/version, model version, dataset fingerprint, code snapshot.
2. Add run-level metrics:
   - duration, row count, auto-accept rate, review rate, failure reason.
3. Add retry policy with dead-letter queue.

**Definition of Done**
- Any run can be replayed with same inputs and version pins.

---

### E. Missing: marimo UX for operations
**Current gap**
- No operator panel for autopilot runs/review actions.

**Fix we can implement now**
In marimo app, create 4 tabs:
1. **Chat/Explore**
2. **Autopilot Runs** (status, logs, rerun)
3. **Review Queue** (approve/correct labels)
4. **Model Health** (confidence trend, drift trend)

**Definition of Done**
- Non-technical user can process low-confidence labels end-to-end without touching backend.

---

## Example Design A: LangChain + LangGraph (recommended for autopilot)

### Why this fits
- LangGraph gives explicit workflow state machine, retries, human-in-the-loop checkpoint, and durable execution — ideal for “new data arrives” automation.

### High-level architecture
1. **Ingestion Node**: fetch new batch from source URI.
2. **Validation Node**: schema checks + basic data quality checks.
3. **Profiling Node**: summary stats + drift report.
4. **Labeling Node**:
   - if approved model exists: predict + confidence.
   - else: call LLM/deep-agent for weak labels.
5. **Confidence Gate Node**:
   - high confidence -> auto accept,
   - low confidence -> human review queue.
6. **Persistence Node**: save labels, metrics, artifacts.
7. **Notification Node**: notify marimo UI / Slack.

### Minimal LangGraph pseudo-code
```python
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END

class AutoPilotState(TypedDict):
    run_id: str
    source_id: str
    dataset_uri: str
    rows: List[Dict[str, Any]]
    valid: bool
    drift_score: float
    predictions: List[Dict[str, Any]]
    review_items: List[Dict[str, Any]]


def ingest(state: AutoPilotState) -> AutoPilotState: ...
def validate(state: AutoPilotState) -> AutoPilotState: ...
def profile_and_drift(state: AutoPilotState) -> AutoPilotState: ...
def label_predict(state: AutoPilotState) -> AutoPilotState: ...
def gate_confidence(state: AutoPilotState) -> AutoPilotState: ...
def persist(state: AutoPilotState) -> AutoPilotState: ...
def notify(state: AutoPilotState) -> AutoPilotState: ...

graph = StateGraph(AutoPilotState)
graph.add_node("ingest", ingest)
graph.add_node("validate", validate)
graph.add_node("profile", profile_and_drift)
graph.add_node("label", label_predict)
graph.add_node("gate", gate_confidence)
graph.add_node("persist", persist)
graph.add_node("notify", notify)

graph.set_entry_point("ingest")
graph.add_edge("ingest", "validate")
graph.add_conditional_edges("validate", lambda s: "profile" if s["valid"] else END)
graph.add_edge("profile", "label")
graph.add_edge("label", "gate")
graph.add_edge("gate", "persist")
graph.add_edge("persist", "notify")
graph.add_edge("notify", END)

app = graph.compile()
```

### Human-in-the-loop behavior
- `gate_confidence` sends uncertain rows to `review_queue`.
- marimo Review tab lets user approve/correct.
- corrected labels are written back and included in retraining dataset.

---

## Example Design B: Deep-Agent-first variant

Use your existing DSPy/deep-agent stack for label suggestion:
1. `preprocessing_agent` standardizes features.
2. `sk_learn_agent` trains/loads baseline model.
3. `deep_analysis_module` explains anomalies and suggests fallback weak labels.
4. policy layer decides final action (`auto_accept` / `needs_review`).

This keeps your current stack intact while adding orchestration around it.

---

## Quick implementation plan (2–4 weeks MVP)

### Week 1
- Add DB tables (`autopilot_runs`, `label_predictions`, `review_queue`, `dataset_contracts`).
- Add `POST /autopilot/ingest-event` and worker skeleton.

### Week 2
- Implement validate + drift + labeling + confidence gate pipeline.
- Expose `GET /autopilot/runs`, `GET /autopilot/runs/{id}`, `POST /labels/review`.

### Week 3
- Build marimo tabs (Runs/Review/Health).
- Add retraining trigger + model registry metadata.

### Week 4 (hardening)
- retries, idempotency, dead-letter, dashboards, alerting.

---

## Final recommendation

For your exact target (**autopilot on new data + auto label data**), choose:
- **LangGraph orchestration** for workflow durability + HITL,
- **existing Auto-Analyst agents** for analytics/code intelligence,
- **marimo** as operator-facing UI.

This is the fastest path that is both practical and extensible.
