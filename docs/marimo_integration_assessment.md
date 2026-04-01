# Marimo Integration Assessment for Auto-Analyst

## Goal
Evaluate whether this repository can be adapted for a **marimo app** workflow where end users can:
1. ask questions in chat,
2. generate and view plots,
3. get analytical/code responses,
4. run an autopilot flow when new data arrives,
5. automatically label new data.

## Current Capability Snapshot

### 1) Chat + multi-agent analysis: **Available now**
- Backend provides chat endpoints for explicit agent routing (`/chat/{agent_name}`) and planner-style flow (`/chat`), with session-aware datasets and model selection.
- Frontend already calls these endpoints and preserves chat context.
- Agent architecture is modular and DSPy-based, so adding task-specific agents is feasible.

### 2) Plot generation and display: **Available now**
- Backend code execution endpoint returns Plotly and Matplotlib outputs in structured blocks.
- Frontend renders Plotly with `react-plotly.js` and supports code execution from chat.
- This is compatible with marimo because marimo can also render Plotly/Matplotlib, but integration glue is required.

### 3) Code execution loop: **Available now**
- Existing `/code/execute` pipeline executes generated code and stores execution metadata.
- Frontend currently triggers this automatically for detected code blocks.

### 4) New-data autopilot trigger: **Partially present (needs implementation)**
- There are streaming/deep-analysis APIs, but no concrete ingestion trigger engine (e.g., webhook/file watcher/job runner) that monitors external data sources and launches analysis jobs automatically.
- README mentions scheduled reports, but repository-level implementation for generalized ingestion/autopilot is not obvious as a standalone orchestration module.

### 5) Auto-labeling new data: **Not productized yet**
- The system has ML/statistics agents and can generate classification code, but there is no explicit end-to-end “auto label incoming records” service flow (model registry + retraining + prediction + confidence threshold + human review queue).

## Feasibility Verdict

## ✅ Can it be used for your marimo use case?
**Yes, with moderate integration work.**

You already have a strong base for:
- LLM-driven analytical chat,
- plot/code generation,
- multi-agent orchestration,
- session-aware execution.

The missing pieces for your exact target are mainly in **MLOps/dataops orchestration** (autopilot trigger + reliable auto-label pipeline), not in core chat analytics.

## Recommended Implementation Plan (for marimo)

### Phase 1 — Embed core chat analytics in marimo (low-medium effort)
- Use Auto-Analyst backend as an API service.
- In marimo:
  - add chat input,
  - call `/chat` or `/chat/{agent}`,
  - parse returned markdown/code blocks,
  - optionally call `/code/execute`,
  - render Plotly/Matplotlib directly in marimo cells.

### Phase 2 — Add autopilot trigger layer (medium effort)
- Add a new “ingestion event” endpoint or queue consumer.
- Trigger on:
  - new file arrival (S3/GCS/local watcher), or
  - webhook from ETL/ELT pipeline.
- Persist each run as a job record (status, logs, artifacts, report URL).

### Phase 3 — Implement production-grade auto labeling (medium-high effort)
- Add dedicated labeling service:
  - choose latest model for dataset domain,
  - run predictions on new rows,
  - confidence thresholding,
  - send low-confidence rows to human review,
  - write labels + provenance metadata.
- Optional: active-learning loop (retrain when reviewed labels accumulate).

## Risks / Gaps to Address
- Generated-code execution security boundaries (sandbox, resource limits, package allowlist).
- Deterministic reproducibility for auto-label runs.
- Drift detection + model versioning for long-term autopilot quality.
- Clear SLAs for latency if marimo app is interactive.

## Bottom Line
For your requirement (chat + plot + analysis + autopilot on new data + auto-labeling), this repository is a **good foundation** but not yet a complete turnkey solution. Build a thin marimo UI adapter first, then add an ingestion/autolabel orchestration layer for full autopilot behavior.
