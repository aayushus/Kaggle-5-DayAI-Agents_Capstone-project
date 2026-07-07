from __future__ import annotations

import json
import asyncio
import queue
import threading
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import load_settings
from app.rate_limit import RateLimitMiddleware, RequestSizeLimitMiddleware
from app.scout.artifact_store import load_market_artifact, save_market_artifact
from app.scout.chat_sessions import append_turn, create_session, get_session
from app.scout.local_mcp_client import read_market_artifact as local_mcp_read_market_artifact
from app.scout.local_mcp_client import write_market_artifact as local_mcp_write_market_artifact
from app.scout.mcp_server import build_mcp_server
from app.scout.orchestrator import ScoutOrchestrator
from app.scout.pdf_export import write_market_pdf
from app.scout.simulators import (
    simulate_competitor_war_room,
    simulate_customer_advisory_board,
    stream_competitor_war_room,
    stream_customer_advisory_board,
)


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
SETTINGS = load_settings()

app = FastAPI(title="Northstar", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, settings=SETTINGS)
app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=5 * 1024 * 1024)

orchestrator = ScoutOrchestrator(output_dir=OUTPUT_DIR, settings=SETTINGS)
mcp_server = build_mcp_server(BASE_DIR, OUTPUT_DIR, SETTINGS)
app.mount("/mcp", mcp_server.sse_app())


class RunRequest(BaseModel):
    concept: str = Field(min_length=5)
    geography: str = Field(min_length=2)
    sector: str = Field(min_length=2)
    funding_scale: str = Field(min_length=2)


class SimulationStartRequest(BaseModel):
    report: dict
    prompt: str = Field(min_length=3)
    market_markdown_path: str | None = None


class SimulationTurnRequest(BaseModel):
    message: str = Field(min_length=2)


TRACK_FILE = OUTPUT_DIR / "visits.json"


def _load_visits() -> list[dict]:
    if TRACK_FILE.exists():
        try:
            return json.loads(TRACK_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_visit(ip: str, user_agent: str, path: str):
    import datetime
    visits = _load_visits()
    new_visit = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ip": ip,
        "user_agent": user_agent,
        "path": path,
    }
    visits.append(new_visit)
    visits = visits[-1000:]
    try:
        TRACK_FILE.write_text(json.dumps(visits, indent=2), encoding="utf-8")
    except Exception:
        pass


@app.get("/", response_class=HTMLResponse)
def root(request: Request) -> HTMLResponse:
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    _save_visit(ip, user_agent, "/")
    return HTMLResponse((BASE_DIR / "frontend" / "index.html").read_text(encoding="utf-8"))


@app.get("/track", response_class=HTMLResponse)
def track_visit(request: Request) -> HTMLResponse:
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    _save_visit(ip, user_agent, "/track")
    visits = _load_visits()
    
    rows = []
    for v in visits[::-1][:100]:
        rows.append(f"""
        <tr>
            <td style="color: var(--muted); font-family: monospace;">{v.get('timestamp', '')}</td>
            <td><strong>{v.get('ip', '')}</strong></td>
            <td><code style="background: var(--bg); padding: 2px 6px; border-radius: 4px;">{v.get('path', '')}</code></td>
            <td class="ua-text">{v.get('user_agent', '')}</td>
        </tr>
        """)
    table_rows = "\n".join(rows)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Northstar - Visitor Tracker</title>
    <style>
        :root {{
            --bg: #f5f5f7;
            --card: #ffffff;
            --ink: #1d1d1f;
            --muted: #86868b;
            --line: #d2d2d7;
            --accent: #0071e3;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #1d1d1f;
                --card: #2d2d2f;
                --ink: #f5f5f7;
                --muted: #86868b;
                --line: #3a3a3c;
                --accent: #2997ff;
            }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--ink);
            margin: 0;
            padding: 40px 20px;
            display: flex;
            justify-content: center;
        }}
        .container {{
            width: 100%;
            max-width: 1000px;
            background: var(--card);
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            padding: 32px;
            box-sizing: border-box;
        }}
        h1 {{
            font-size: 1.8rem;
            font-weight: 700;
            margin-top: 0;
            margin-bottom: 24px;
            letter-spacing: -0.02em;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }}
        .meta-card {{
            background: var(--bg);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px;
        }}
        .meta-card span {{
            display: block;
            font-size: 0.8rem;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 4px;
        }}
        .meta-card strong {{
            font-size: 1.1rem;
            font-weight: 600;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid var(--line);
        }}
        th {{
            font-weight: 600;
            color: var(--muted);
        }}
        tr:hover td {{
            background: rgba(0,0,0,0.02);
        }}
        .ua-text {{
            font-size: 0.8rem;
            color: var(--muted);
            word-break: break-all;
        }}
        .back-link {{
            display: inline-block;
            margin-bottom: 20px;
            color: var(--accent);
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
        }}
        .back-link:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">&larr; Back to Northstar Workspace</a>
        <h1>🧭 Northstar Visitor Logs</h1>
        <div class="meta-grid">
            <div class="meta-card">
                <span>Total Visits Logged</span>
                <strong>{len(visits)}</strong>
            </div>
            <div class="meta-card">
                <span>Your Client IP</span>
                <strong>{ip}</strong>
            </div>
        </div>
        
        <h2 style="font-size: 1.3rem; margin-bottom: 16px;">Recent Activity (Last 100 visits)</h2>
        <div style="overflow-x: auto; border: 1px solid var(--line); border-radius: 8px;">
            <table>
                <thead>
                    <tr style="background: var(--bg);">
                        <th>Time (UTC)</th>
                        <th>IP Address</th>
                        <th>Path</th>
                        <th>User Agent</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(html_content)


@app.get("/static/{path:path}")
def static_files(path: str):
    file_path = BASE_DIR / "frontend" / path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(file_path)


@app.get("/api/brief")
def brief(concept: str):
    return {
        "concept": concept,
        "questions": [
            "What geography should this target first?",
            "Which sector or subcategory matters most?",
            "What funding stage and scale assumptions should Northstar use?",
        ],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "adk_backend_preference": SETTINGS.adk_backend,
        "adk_backend_selected": orchestrator.runtime.backend,
        "google_model": SETTINGS.google_model,
        "google_api_key_present": SETTINGS.google_api_key_present,
        "google_use_vertexai": SETTINGS.google_use_vertexai,
        "google_adk_ready": orchestrator.google_adk.status.ready,
        "google_adk_reason": orchestrator.google_adk.status.reason,
        "parallel_api_key_present": SETTINGS.parallel_api_key_present,
        "parallel_search_mode": SETTINGS.parallel_search_mode,
        "parallel_search_mcp_enabled": SETTINGS.parallel_search_mcp_enabled,
        "parallel_search_mcp_url": SETTINGS.parallel_search_mcp_url,
        "local_mcp_enabled": SETTINGS.local_mcp_enabled,
        "local_mcp_url": SETTINGS.local_mcp_url,
        "mcp_server_enabled": True,
    }


@app.get("/api/artifacts/pdf")
def artifact_pdf(path: str):
    artifact_path = _resolve_output_path(path)
    report, markdown_text = None, None
    if SETTINGS.local_mcp_enabled:
        try:
            loaded = local_mcp_read_market_artifact(str(artifact_path), url=SETTINGS.local_mcp_url)
            if loaded:
                report = loaded.get("report")
                markdown_text = loaded.get("market_markdown")
        except Exception:
            pass
    if not report or not markdown_text:
        report, markdown_text = load_market_artifact(str(artifact_path))
    pdf_path = artifact_path.with_suffix(".pdf")
    write_market_pdf(markdown_text or save_market_artifact(str(artifact_path), report), pdf_path)
    return FileResponse(str(pdf_path), media_type="application/pdf", filename=pdf_path.name)


@app.post("/api/run")
def run(request: RunRequest):
    result = orchestrator.run(request.model_dump())
    return asdict(result)


@app.post("/api/run/stream")
def run_stream(request: RunRequest):
    q: queue.Queue[str | None] = queue.Queue()
    result_box: dict[str, object] = {}

    def emit(message: str) -> None:
        q.put(message)

    def worker() -> None:
        try:
            result_box["result"] = orchestrator.run(request.model_dump(), emit=emit)
        except Exception as exc:
            result_box["error"] = str(exc)
            q.put(f"ERROR: {exc}")
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def event_stream():
        while True:
            message = await asyncio.to_thread(q.get)
            if message is None:
                break
            yield f"data: {json.dumps({'type': 'trace', 'message': message})}\n\n"
        result = result_box.get("result")
        if result is not None:
            yield f"data: {json.dumps({'type': 'result', 'payload': asdict(result)})}\n\n"
        error = result_box.get("error")
        if error is not None:
            yield f"data: {json.dumps({'type': 'error', 'message': error})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/simulate/board")
def simulate_board(request: RunRequest):
    result = orchestrator.run(request.model_dump())
    return simulate_customer_advisory_board(result.report, request.concept)


@app.post("/api/simulate/board/stream")
def simulate_board_stream(request: RunRequest):
    result = orchestrator.run(request.model_dump())
    return StreamingResponse(stream_customer_advisory_board(result.report, request.concept), media_type="text/event-stream")


@app.post("/api/simulate/war-room")
def simulate_war_room(request: RunRequest):
    result = orchestrator.run(request.model_dump())
    return simulate_competitor_war_room(result.report, request.concept)


@app.post("/api/simulate/war-room/stream")
def simulate_war_room_stream(request: RunRequest):
    result = orchestrator.run(request.model_dump())
    return StreamingResponse(stream_competitor_war_room(result.report, request.concept), media_type="text/event-stream")


@app.post("/api/sessions/board")
def create_board_session(request: SimulationStartRequest):
    report = _resolve_session_report(request.report, request.market_markdown_path)
    session = create_session("board", report, request.prompt, market_markdown_path=request.market_markdown_path)
    append_turn(session, "user", request.prompt)
    payload = _board_payload(session.report, request.prompt, session.history, session_id=session.session_id)
    updated_report = _apply_board_feedback_to_report(session.report, payload)
    updated_market_markdown = _persist_session_report(session, updated_report)
    append_turn(session, "assistant", payload["reply"], payload)
    return {
        "session_id": session.session_id,
        "kind": session.kind,
        "payload": payload,
        "history": session.history,
        "updated_report": updated_report,
        "updated_market_markdown": updated_market_markdown,
    }


@app.post("/api/sessions/board/{session_id}/stream")
def continue_board_session(session_id: str, request: SimulationTurnRequest):
    try:
        session = get_session(session_id, "board")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Board session not found") from exc
    append_turn(session, "user", request.message)

    async def event_stream():
        payload = _board_payload(session.report, request.message, session.history, session_id=session.session_id)
        updated_report = _apply_board_feedback_to_report(session.report, payload)
        updated_market_markdown = _persist_session_report(session, updated_report)
        yield f"data: {json.dumps({'type': 'trace', 'message': 'Northstar is updating the advisory board with the latest context.'})}\n\n"
        yield f"data: {json.dumps({'type': 'result', 'payload': payload})}\n\n"
        append_turn(session, "assistant", payload["reply"], payload)
        yield f"data: {json.dumps({'type': 'report_update', 'payload': updated_report})}\n\n"
        yield f"data: {json.dumps({'type': 'artifact_update', 'payload': {'market_markdown': updated_market_markdown, 'market_markdown_path': session.market_markdown_path}})}\n\n"
        yield f"data: {json.dumps({'type': 'history', 'payload': session.history})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/sessions/board/{session_id}")
def continue_board_session_json(session_id: str, request: SimulationTurnRequest):
    try:
        session = get_session(session_id, "board")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Board session not found") from exc
    append_turn(session, "user", request.message)
    payload = _board_payload(session.report, request.message, session.history, session_id=session.session_id)
    updated_report = _apply_board_feedback_to_report(session.report, payload)
    updated_market_markdown = _persist_session_report(session, updated_report)
    append_turn(session, "assistant", payload["reply"], payload)
    return {
        "session_id": session.session_id,
        "kind": session.kind,
        "payload": payload,
        "history": session.history,
        "updated_report": updated_report,
        "updated_market_markdown": updated_market_markdown,
        "market_markdown_path": session.market_markdown_path,
    }


@app.post("/api/sessions/war-room")
def create_war_session(request: SimulationStartRequest):
    report = _resolve_session_report(request.report, request.market_markdown_path)
    session = create_session("war-room", report, request.prompt, market_markdown_path=request.market_markdown_path)
    append_turn(session, "user", request.prompt)
    payload = _war_payload(session.report, request.prompt, session.history, session_id=session.session_id)
    updated_report = _apply_war_feedback_to_report(session.report, payload)
    updated_market_markdown = _persist_session_report(session, updated_report)
    append_turn(session, "assistant", payload["reply"], payload)
    return {
        "session_id": session.session_id,
        "kind": session.kind,
        "payload": payload,
        "history": session.history,
        "updated_report": updated_report,
        "updated_market_markdown": updated_market_markdown,
    }


@app.post("/api/sessions/war-room/{session_id}/stream")
def continue_war_session(session_id: str, request: SimulationTurnRequest):
    try:
        session = get_session(session_id, "war-room")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="War room session not found") from exc
    append_turn(session, "user", request.message)

    async def event_stream():
        yield f"data: {json.dumps({'type': 'trace', 'message': 'Northstar is rerunning the competitive threat model.'})}\n\n"
        payload = _war_payload(session.report, request.message, session.history, session_id=session.session_id)
        updated_report = _apply_war_feedback_to_report(session.report, payload)
        updated_market_markdown = _persist_session_report(session, updated_report)
        yield f"data: {json.dumps({'type': 'result', 'payload': payload})}\n\n"
        append_turn(session, "assistant", payload["reply"], payload)
        yield f"data: {json.dumps({'type': 'report_update', 'payload': updated_report})}\n\n"
        yield f"data: {json.dumps({'type': 'artifact_update', 'payload': {'market_markdown': updated_market_markdown, 'market_markdown_path': session.market_markdown_path}})}\n\n"
        yield f"data: {json.dumps({'type': 'history', 'payload': session.history})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/sessions/war-room/{session_id}")
def continue_war_session_json(session_id: str, request: SimulationTurnRequest):
    try:
        session = get_session(session_id, "war-room")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="War room session not found") from exc
    append_turn(session, "user", request.message)
    payload = _war_payload(session.report, request.message, session.history, session_id=session.session_id)
    updated_report = _apply_war_feedback_to_report(session.report, payload)
    updated_market_markdown = _persist_session_report(session, updated_report)
    append_turn(session, "assistant", payload["reply"], payload)
    return {
        "session_id": session.session_id,
        "kind": session.kind,
        "payload": payload,
        "history": session.history,
        "updated_report": updated_report,
        "updated_market_markdown": updated_market_markdown,
        "market_markdown_path": session.market_markdown_path,
    }


def _board_payload(report: dict, prompt: str, history: list[dict], session_id: str | None = None) -> dict:
    adk_payload = orchestrator.google_adk.simulate_advisory_board_turn(report, prompt, history, session_id=session_id)
    if adk_payload:
        return adk_payload
    payload = simulate_customer_advisory_board(report, prompt, history=history)
    payload["generator"] = "local-fallback"
    return payload


def _war_payload(report: dict, prompt: str, history: list[dict], session_id: str | None = None) -> dict:
    adk_payload = orchestrator.google_adk.simulate_war_room_turn(report, prompt, history, session_id=session_id)
    if adk_payload:
        return adk_payload
    payload = simulate_competitor_war_room(report, prompt, history=history)
    payload["generator"] = "local-fallback"
    return payload


def _apply_board_feedback_to_report(report: dict, payload: dict) -> dict:
    blueprint = report.setdefault("landing_page_blueprint", {})
    responses = payload.get("responses", [])
    friction_points: list[str] = []
    requested_changes: list[str] = []
    for item in responses:
        friction_points.extend(_coerce_text_list(item.get("friction_points")))
        requested_changes.extend(_coerce_text_list(item.get("requested_changes")))

    objection_copy = []
    for point in friction_points[:2]:
        objection_copy.append(f"Buyer concern: {point}")
    for change in requested_changes[:2]:
        objection_copy.append(f"Northstar response: {change}")
    if objection_copy:
        blueprint["objection_handling_copy"] = objection_copy

    recommendation = payload.get("recommendation")
    blocking_issue = payload.get("blocking_issue")
    fit_scores = payload.get("fit_scores", {})
    refined_hooks = []
    if recommendation:
        refined_hooks.append(recommendation)
    if blocking_issue:
        refined_hooks.append(f"Designed to reduce {blocking_issue}.")
    if fit_scores:
        ranked = sorted(fit_scores.items(), key=lambda item: item[1], reverse=True)
        refined_hooks.extend(
            f"Strength: {key.replace('_', ' ')} scored {_format_fit_score(value)}."
            for key, value in ranked[:2]
        )
    if refined_hooks:
        current_hooks = list(blueprint.get("value_hooks", []))
        blueprint["value_hooks"] = (refined_hooks + current_hooks)[:4]
    simulation_state = report.get("simulation_state") or {}
    report["simulation_state"] = simulation_state
    simulation_state["latest_board_feedback"] = payload
    return report


def _apply_war_feedback_to_report(report: dict, payload: dict) -> dict:
    simulation_state = report.get("simulation_state") or {}
    report["simulation_state"] = simulation_state
    simulation_state["latest_war_room"] = payload
    blueprint = report.setdefault("landing_page_blueprint", {})
    counter_moves = list(payload.get("counter_moves", []))
    if counter_moves:
        current_hooks = list(blueprint.get("value_hooks", []))
        war_hooks = [f"Defensive edge: {move}" for move in counter_moves[:2]]
        merged_hooks: list[str] = []
        for hook in war_hooks + current_hooks:
            if hook and hook not in merged_hooks:
                merged_hooks.append(hook)
        blueprint["value_hooks"] = merged_hooks[:4]
    return report


def _resolve_session_report(request_report: dict, market_markdown_path: str | None) -> dict:
    if market_markdown_path:
        try:
            loaded: dict | None = None
            if SETTINGS.local_mcp_enabled:
                loaded = local_mcp_read_market_artifact(market_markdown_path, url=SETTINGS.local_mcp_url)
            if loaded:
                report = loaded.get("report") or {}
            else:
                report, _ = load_market_artifact(market_markdown_path)
            if request_report.get("audit") and not report.get("audit"):
                report["audit"] = request_report.get("audit")
            return report
        except Exception:
            pass
    return request_report


def _resolve_output_path(path: str) -> Path:
    candidate = Path(path).expanduser().resolve()
    output_root = OUTPUT_DIR.resolve()
    if output_root not in candidate.parents and candidate != output_root:
        raise HTTPException(status_code=400, detail="Artifact path must be inside the output directory.")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return candidate


def _persist_session_report(session, report: dict) -> str | None:
    session.report = report
    if not session.market_markdown_path:
        return None
    if SETTINGS.local_mcp_enabled:
        updated = local_mcp_write_market_artifact(session.market_markdown_path, report, url=SETTINGS.local_mcp_url)
        if updated is not None:
            return updated
    return save_market_artifact(session.market_markdown_path, report)


def _coerce_text_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _format_fit_score(value) -> str:
    try:
        numeric = float(value)
    except Exception:
        return str(value)
    if numeric <= 5:
        return f"{numeric:g}/5"
    return f"{numeric:g}/100"
