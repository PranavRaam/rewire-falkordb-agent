"""Loopback presentation API. FalkorDB owns decisions and execution evidence.

The local manifest stores scenario settings and UI history, never provider truth.
One process executes at most one recovery; the independent evaluator is exposed
only to the operator UI and never registered as an agent/MCP tool.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Literal
import urllib.request
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from rewire.fixtures import base_scenario, with_carrier_d, ms_after
from rewire.graph.store import GraphStore, load_query, result_rows
from rewire.planner.engine import ConditionalPlanner
from rewire.recovery import preview_recovery, SimulatorClient
from rewire.mcp_server import inspect_run, authorize_recovery

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "console"
LOCK = threading.RLock()
JOBS: dict[str, bool] = {}
PROCESSES: dict[str, subprocess.Popen] = {}
SCENARIOS = [
    {"id": "base", "name": "The missing response", "subtitle": "Carrier B · response lost after booking", "description": "Carrier A is disabled. Discover a compatible route, then recover the booking receipt after a deliberately lost response."},
    {"id": "carrier-d", "name": "A different way forward", "subtitle": "Carrier D · changed tool catalog", "description": "Carrier B is disabled and Carrier D contracts are added. The same planner must discover a different chain."},
    {"id": "expired", "name": "Know when to stop", "subtitle": "Expired reservation · no safe plan", "description": "The reservation expires at the synthetic clock boundary. A safe agent must refuse to ship."},
]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def manifest_path(run_id: str) -> Path:
    if not run_id.startswith("run-") or len(run_id) != 16 or any(c not in "0123456789abcdef" for c in run_id[4:]):
        raise HTTPException(404, "Unknown run")
    return DATA / run_id / "manifest.json"


def read_manifest(run_id):
    with LOCK:
        path = manifest_path(run_id)
        if not path.exists():
            raise HTTPException(404, "Unknown run")
        return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(value):
    with LOCK:
        path = manifest_path(value["runId"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temp.replace(path)


def update_manifest(run_id, **values):
    with LOCK:
        manifest = read_manifest(run_id)
        manifest.update(values)
        save_manifest(manifest)


def query(graph, name, run_id):
    return result_rows(graph.ro_query(load_query(name), {"runId": run_id}))


def snapshot(run_id):
    meta = read_manifest(run_id)
    store = GraphStore()
    try:
        graph = store.select(meta["graphName"])
        state = inspect_run(meta["graphName"], run_id)
        steps = query(graph, "Q18_console_steps", run_id)
        artifacts = [r["artifact"] for r in query(graph, "Q19_console_artifacts", run_id)]
        events = query(graph, "Q20_console_events", run_id)
        return {**meta, "state": state, "executionSteps": steps,
                "artifacts": artifacts, "events": events,
                "busy": JOBS.get(run_id, False), "mode": "LIVE_SYNTHETIC",
                "interrupted": meta.get("jobStatus") == "RUNNING" and not JOBS.get(run_id, False)}
    finally:
        store.close()


def start_provider(meta):
    run_id = meta["runId"]
    current = PROCESSES.get(run_id)
    if current is not None and current.poll() is None:
        return meta["providerUrl"]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    db = manifest_path(run_id).parent / "world.sqlite3"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "services" / "simulator")}
    args = [sys.executable, "-m", "rewire_simulator", "--port", str(port),
            "--db", str(db), "--now-ms", str(meta["nowMs"])]
    if meta["faultAfterCommit"]:
        args += ["--fault-after-commit", "booking"]
    proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    PROCESSES[run_id] = proc
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 12
        while True:
            try:
                SimulatorClient(base).now()
                break
            except OSError:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise RuntimeError("The independent provider simulator did not start")
                time.sleep(.1)
        update_manifest(run_id, providerUrl=base)
        return base
    except Exception:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        raise


def execute_job(run_id, digest, mode):
    started = time.perf_counter()
    try:
        meta = read_manifest(run_id)
        provider_url = start_provider(meta)
        from rewire.agent import run_agent, _call_mcp_tool
        if mode == "model":
            result = run_agent("Execute the approved recovery and verify the booking evidence.",
                               meta["graphName"], run_id, meta["nowMs"],
                               approved_digest=digest, provider_url=provider_url, max_tool_rounds=10)
        else:
            with authorize_recovery(meta["graphName"], run_id, digest, provider_url):
                result = _call_mcp_tool("execute_approved_recovery", {
                    "graph_name": meta["graphName"], "run_id": run_id})
        success = result.get("status") in ("SUCCEEDED", "COMPLETE")
        update_manifest(run_id, executionResult=result, jobStatus="FINISHED",
                        error=None if success else result.get("reason", result.get("final", "Recovery requires reconciliation; no success is claimed.")),
                        elapsedMs=round((time.perf_counter()-started)*1000), finishedAt=stamp())
    except Exception as exc:
        update_manifest(run_id, jobStatus="ERROR", error=f"{type(exc).__name__}: {exc}")
    finally:
        with LOCK:
            JOBS[run_id] = False
        proc = PROCESSES.pop(run_id, None)
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


@asynccontextmanager
async def lifespan(app):
    DATA.mkdir(parents=True, exist_ok=True)
    lockfile = (DATA / "coordinator.lock").open("a+b")
    lockfile.seek(0)
    if os.name == "nt":
        import msvcrt
        lockfile.write(b"0")
        lockfile.flush()
        lockfile.seek(0)
        msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        yield
    finally:
        for proc in list(PROCESSES.values()):
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        lockfile.close()


app = FastAPI(title="Rewire control room", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])


@app.middleware("http")
async def local_mutations(request: Request, call_next):
    # No CORS and a mandatory custom header block browser cross-site form writes.
    if request.method == "POST":
        if request.headers.get("x-rewire-client") != "control-room":
            return JSONResponse({"detail": "Use the local Rewire control room"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in {f"http://{request.headers.get('host')}", "http://127.0.0.1:5173", "http://localhost:5173"}:
            return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def failure(request, exc):
    return JSONResponse({"detail": f"{type(exc).__name__}: {exc}",
                         "code": "DEPENDENCY_UNAVAILABLE"}, status_code=503)


class CreateRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["base", "carrier-d", "expired"] = "base"
    faultAfterCommit: bool = True


class ExecuteRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approvalDigest: str = Field(min_length=64, max_length=64, pattern="^[a-f0-9]+$")
    mode: Literal["model", "direct"] = "model"


@app.get("/api/health")
def health():
    graph_ok, model_ok = False, False
    try:
        store = GraphStore()
        try:
            graph_ok = bool(store.client.connection.ping())
        finally:
            store.close()
    except Exception:
        pass
    model = os.getenv("REWIRE_LLM_MODEL", "qwen3.5:4b")
    if os.getenv("REWIRE_LLM_PROVIDER", "ollama") == "ollama":
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                    "http://127.0.0.1:11434/api/tags", timeout=2) as response:
                model_ok = any(m["name"] == model for m in json.load(response).get("models", []))
        except Exception:
            pass
    return {"graph": graph_ok, "model": model, "modelAvailable": model_ok,
            "environment": "local synthetic", "singleCoordinator": True}


@app.get("/api/scenarios")
def scenarios():
    return SCENARIOS


@app.get("/api/runs")
def list_runs():
    result = []
    for path in DATA.glob("run-*/manifest.json"):
        meta = read_manifest(path.parent.name)
        result.append({key: meta.get(key) for key in ("runId", "scenario", "createdAt", "jobStatus")})
    return sorted(result, key=lambda r: r["createdAt"], reverse=True)[:50]


@app.post("/api/runs", status_code=201)
def create_run(body: CreateRun):
    with LOCK:
        if any(JOBS.values()):
            raise HTTPException(409, "Wait for the active recovery to finish before starting a new experiment")
        token = uuid.uuid4().hex[:12]
        run_id, graph_name = f"run-{token}", f"rewire_phase1_{token}"
        scenario = base_scenario()
        if body.scenario == "carrier-d":
            scenario = with_carrier_d(scenario)
            scenario = replace(scenario, tools=tuple(replace(t, enabled=False)
                if t.tool_id.startswith("carrier-b-") else t for t in scenario.tools))
        scenario = replace(scenario, run_id=run_id,
                           now_ms=ms_after(20) if body.scenario == "expired" else scenario.now_ms)
        meta = {"runId":run_id, "graphName":graph_name, "scenario":body.scenario,
                "nowMs":scenario.now_ms, "createdAt":stamp(), "jobStatus":"READY",
                "faultAfterCommit":body.faultAfterCommit, "plan":None, "approvalDigest":None}
        save_manifest(meta)  # Ownership is recorded before any database writes.
        store = GraphStore()
        try:
            store.install_schema(graph_name)
            store.seed(graph_name, scenario)
            planner = ConditionalPlanner(store, graph_name, run_id, scenario.goal, scenario.now_ms, 1)
            plan = planner.discover()
            digest = (preview_recovery(graph_name, run_id, scenario.now_ms)["approvalDigest"]
                      if plan["status"] == "STRUCTURALLY_VALID" else None)
            update_manifest(run_id, plan=plan, approvalDigest=digest)
        except Exception as exc:
            update_manifest(run_id, jobStatus="ERROR", error=str(exc))
            raise
        finally:
            store.close()
        return snapshot(run_id)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return snapshot(run_id)


@app.post("/api/runs/{run_id}/execute", status_code=202)
def execute(run_id: str, body: ExecuteRun):
    with LOCK:
        meta = read_manifest(run_id)
        if meta.get("approvalDigest") != body.approvalDigest:
            raise HTTPException(409, "Approval does not match this plan")
        if JOBS.get(run_id):
            return {"status":"RUNNING", "runId":run_id}
        if any(JOBS.values()):
            raise HTTPException(409, "Another recovery is running in this single coordinator")
        update_manifest(run_id, jobStatus="RUNNING", executionMode=body.mode,
                        approvedAt=stamp(), error=None)
        JOBS[run_id] = True
        threading.Thread(target=execute_job, args=(run_id, body.approvalDigest, body.mode), daemon=True).start()
        return {"status":"RUNNING", "runId":run_id}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, request: Request):
    read_manifest(run_id)
    async def stream():
        previous = None
        while not await request.is_disconnected():
            try:
                value = await asyncio.to_thread(snapshot, run_id)
                encoded = json.dumps(value, sort_keys=True)
                if encoded != previous:
                    yield f"event: snapshot\ndata: {encoded}\n\n"
                    previous = encoded
                else:
                    yield ": keepalive\n\n"
            except Exception:
                yield 'event: unavailable\ndata: {"message":"Graph unavailable. Actions are disabled until reconnection."}\n\n'
            await asyncio.sleep(.65)
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache", "X-Accel-Buffering":"no"})


@app.get("/api/runs/{run_id}/audit")
def audit(run_id: str):
    read_manifest(run_id)
    if JOBS.get(run_id):
        raise HTTPException(409, "The independent audit becomes available when execution settles")
    path = manifest_path(run_id).parent / "world.sqlite3"
    if not path.exists():
        raise HTTPException(409, "No provider operations have been performed")
    with sqlite3.connect(path.as_uri()+"?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ("bookings", "operations", "pickups", "quotes", "labels")}
        bookings = [dict(r) for r in db.execute("SELECT * FROM bookings")]
    return {"source":"Independent provider SQLite ledger · read-only evaluator",
            "visibleToAgent":False, "rowCounts":counts, "bookings":bookings}


@app.get("/api/runs/{run_id}/export")
def export(run_id: str):
    value = snapshot(run_id)
    try:
        value["independentAudit"] = audit(run_id)
    except HTTPException:
        value["independentAudit"] = None
    value.pop("providerUrl", None)
    return JSONResponse(value, headers={"Content-Disposition":f'attachment; filename="rewire-{run_id}.json"'})


DIST = ROOT / "apps" / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/favicon.svg")
def favicon():
    return FileResponse(ROOT / "apps" / "web" / "public" / "favicon.svg")


@app.get("/")
def index():
    if not (DIST / "index.html").exists():
        raise HTTPException(503, "Build the UI first: cd apps/web; npm ci; npm run build")
    return FileResponse(DIST / "index.html")
