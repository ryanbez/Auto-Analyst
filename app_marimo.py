import base64
import json
import os
import re
from typing import Any, Dict, List

import requests

try:
    import marimo as mo
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "marimo is not installed. Run: pip install marimo requests plotly"
    ) from exc


app = mo.App(width="wide")


def _default_backend_url() -> str:
    return os.getenv("AUTO_ANALYST_API_URL", "http://localhost:8000")


def _build_headers(session_id: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if session_id.strip():
        headers["X-Session-ID"] = session_id.strip()
    return headers


def _query_params(user_id: str, chat_id: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if user_id.strip():
        params["user_id"] = int(user_id)
    if chat_id.strip():
        params["chat_id"] = int(chat_id)
    return params


def send_chat(
    api_url: str,
    query: str,
    session_id: str,
    user_id: str,
    chat_id: str,
    agent_name: str,
    timeout: int = 180,
) -> Dict[str, Any]:
    endpoint = f"{api_url.rstrip('/')}/chat"
    if agent_name != "planner":
        endpoint = f"{api_url.rstrip('/')}/chat/{agent_name}"

    response = requests.post(
        endpoint,
        params=_query_params(user_id, chat_id),
        headers=_build_headers(session_id),
        json={"query": query},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def execute_python(api_url: str, code: str, session_id: str, timeout: int = 180) -> Dict[str, Any]:
    endpoint = f"{api_url.rstrip('/')}/code/execute"
    response = requests.post(
        endpoint,
        headers=_build_headers(session_id),
        json={"code": code, "session_id": session_id or None},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def extract_python_blocks(markdown_text: str) -> List[str]:
    pattern = re.compile(r"```python\n([\s\S]*?)```", re.MULTILINE)
    return [m.strip() for m in pattern.findall(markdown_text or "") if m.strip()]


def parse_plotly_outputs(exec_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    outputs = exec_payload.get("plotly_outputs") or []
    figs: List[Dict[str, Any]] = []
    for block in outputs:
        cleaned = block.replace("```plotly", "").replace("```", "").strip()
        if cleaned:
            try:
                figs.append(json.loads(cleaned))
            except json.JSONDecodeError:
                pass
    return figs


def parse_matplotlib_outputs(exec_payload: Dict[str, Any]) -> List[bytes]:
    outputs = exec_payload.get("matplotlib_outputs") or []
    images: List[bytes] = []
    for block in outputs:
        cleaned = block.replace("```matplotlib", "").replace("```", "").strip()
        if cleaned:
            try:
                images.append(base64.b64decode(cleaned))
            except Exception:
                pass
    return images


@app.cell
def _():
    mo.md(
        """
# app_marimo.py (MVP)

Run:
```bash
marimo run app_marimo.py
```

This app is ready for:
- Chat with Auto-Analyst backend (`/chat`, `/chat/{agent}`)
- Optional auto-execution of generated Python via `/code/execute`
- Plot rendering from Plotly + Matplotlib outputs
- Autopilot ingestion event payload drafting
"""
    )
    return


@app.cell
def _():
    api_url = mo.ui.text(value=_default_backend_url(), label="Backend API URL")
    session_id = mo.ui.text(value="", label="Session ID (optional)")
    user_id = mo.ui.text(value="", label="User ID (optional)")
    chat_id = mo.ui.text(value="", label="Chat ID (optional)")
    agent = mo.ui.dropdown(
        options=["planner", "preprocessing_agent", "statistical_analytics_agent", "sk_learn_agent", "data_viz_agent"],
        value="planner",
        label="Agent",
    )
    query = mo.ui.text_area(value="Analyze this dataset and show one chart.", label="Prompt")
    auto_execute = mo.ui.checkbox(value=True, label="Auto-execute python blocks")
    run_chat = mo.ui.run_button(label="Send Chat")

    mo.vstack(
        [
            mo.hstack([api_url, session_id]),
            mo.hstack([user_id, chat_id, agent]),
            query,
            mo.hstack([auto_execute, run_chat]),
        ]
    )
    return agent, api_url, auto_execute, chat_id, query, run_chat, session_id, user_id


@app.cell
def _(agent, api_url, auto_execute, chat_id, query, run_chat, session_id, user_id):
    chat_payload = None
    exec_payload = None

    if run_chat.value:
        try:
            chat_payload = send_chat(
                api_url=api_url.value,
                query=query.value,
                session_id=session_id.value,
                user_id=user_id.value,
                chat_id=chat_id.value,
                agent_name=agent.value,
            )
            response_text = chat_payload.get("response", "")
            mo.md("## Chat Response")
            mo.md(response_text if response_text else "(empty response)")

            blocks = extract_python_blocks(response_text)
            if blocks:
                mo.md(f"Found **{len(blocks)}** python block(s).")
                if auto_execute.value:
                    exec_payload = execute_python(
                        api_url=api_url.value,
                        code="\n\n".join(blocks),
                        session_id=session_id.value,
                    )
            else:
                mo.md("No Python code blocks found.")
        except Exception as exc:
            mo.md(f"❌ Error: `{exc}`")
    else:
        mo.md("_Press Send Chat to run._")

    return chat_payload, exec_payload


@app.cell
def _(chat_payload):
    if chat_payload:
        mo.md("## Raw Chat Payload")
        mo.md("```json\n" + json.dumps(chat_payload, indent=2, ensure_ascii=False) + "\n```")
    return


@app.cell
def _(exec_payload):
    if not exec_payload:
        mo.md("No execution payload yet.")
        return

    mo.md("## Code Execution Output")
    output_text = exec_payload.get("output") or ""
    if output_text:
        mo.md("```text\n" + output_text + "\n```")

    for i, fig_spec in enumerate(parse_plotly_outputs(exec_payload), start=1):
        mo.md(f"### Plotly Chart {i}")
        mo.ui.plotly(fig_spec)

    for i, image_bytes in enumerate(parse_matplotlib_outputs(exec_payload), start=1):
        mo.md(f"### Matplotlib Chart {i}")
        mo.image(image_bytes)

    mo.md("## Raw Execution Payload")
    mo.md("```json\n" + json.dumps(exec_payload, indent=2, ensure_ascii=False) + "\n```")
    return


@app.cell
def _():
    mo.md("## Autopilot Event Payload Builder")
    source_id = mo.ui.text(value="crm_leads", label="source_id")
    dataset_uri = mo.ui.text(value="s3://bucket/path/new_batch.parquet", label="dataset_uri")
    schema_version = mo.ui.text(value="v1", label="schema_version")
    event_time = mo.ui.text(value="2026-04-01T00:00:00Z", label="event_time")
    idempotency_key = mo.ui.text(value="crm_leads_2026-04-01_batch-001", label="idempotency_key")

    mo.vstack([source_id, dataset_uri, schema_version, event_time, idempotency_key])

    payload = {
        "source_id": source_id.value,
        "dataset_uri": dataset_uri.value,
        "schema_version": schema_version.value,
        "event_time": event_time.value,
        "idempotency_key": idempotency_key.value,
    }
    mo.md("```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```")
    return


if __name__ == "__main__":
    app.run()
