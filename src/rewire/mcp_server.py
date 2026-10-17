"""MCP tools backed by project-owned FalkorDB graphs.

Action tools require a scoped authorization installed by the trusted host.
The model has no approval tool, provider credentials or raw HTTP endpoint tool.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from contextlib import contextmanager
from typing import Any

from mcp.server import MCPServer

from rewire.domain import Goal
from rewire.graph.store import GraphStore, load_query, result_rows
from rewire.planner.engine import ConditionalPlanner

mcp = MCPServer("Rewire Connected-Data Agent")
_authorizations: dict[tuple[str, str], tuple[str, str]] = {}


@contextmanager
def authorize_recovery(graph_name: str, run_id: str, digest: str, provider_url: str):
    """Trusted host boundary; deliberately not registered as an MCP tool."""
    from rewire.recovery import EXECUTION_LOCK
    with EXECUTION_LOCK:
        scope = (graph_name, run_id)
        if scope in _authorizations:
            raise RuntimeError("another host session already owns this run")
        _authorizations[scope] = (digest, provider_url)
    try:
        yield
    finally:
        _authorizations.pop(scope, None)


@mcp.tool()
def execute_approved_recovery(graph_name: str, run_id: str) -> dict[str, Any]:
    """Execute or reconcile the host-approved plan, with graph preflight and durable receipts."""
    from rewire.recovery import RecoverySession
    authorization = _authorizations.get((graph_name, run_id))
    if authorization is None:
        return {"status": "REJECTED",
                "reason": "trusted host approval is required; model text cannot grant approval"}
    digest, provider_url = authorization
    session = RecoverySession(graph_name, run_id, provider_url)
    try:
        try:
            return session.execute(digest)
        except ValueError as exc:
            return {"status": "REJECTED", "reason": str(exc)}
    finally:
        session.close()


def _require_loopback(host: str) -> None:
    if host.lower() == "localhost":
        return
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError("MCP HTTP transport is restricted to loopback; configure an authenticated gateway separately")
    except ValueError as exc:
        if "restricted to loopback" in str(exc):
            raise
        raise ValueError("MCP HTTP host must be localhost or a loopback IP") from exc


def _store_graph(graph_name: str):
    store = GraphStore()
    try:
        graph = store.select(graph_name)
        return store, graph
    except Exception:
        store.close()
        raise


@mcp.tool()
def inspect_run(graph_name: str, run_id: str) -> dict[str, Any]:
    """Read the run's goal, revision, selected plan and unresolved effects from FalkorDB."""
    store, graph = _store_graph(graph_name)
    try:
        rows = result_rows(graph.ro_query(load_query("Q15_run_goal"), {"runId": run_id}))
        if not rows:
            raise ValueError("run or goal not found in the requested project graph")
        effects = [{"effectId": r["effectId"], "state": r["effectState"],
                    "intentId": r["intentId"], "intentStatus": r["intentStatus"],
                    "operationKey": r["operationKey"]}
                   for r in rows if r.get("effectId")]
        first = rows[0]
        return {"runId": first["runId"], "runStatus": first["runStatus"],
                "revision": first["revision"], "catalogRevision": first["catalogRevision"],
                "selectedPlanId": first["selectedPlanId"],
                "goal": {"goalId": first["goalId"], "outputType": first["outputType"],
                    "orderId": first["orderId"], "warehouseId": first["warehouseId"],
                    "destinationZone": first["destinationZone"], "weightKg": first["weightKg"],
                    "maxCostUnits": first["maxCostUnits"], "cutoffAt": first["cutoffAt"]},
                "effects": effects, "source": "FalkorDB Q15_run_goal"}
    finally:
        store.close()


@mcp.tool()
def discover_recovery(graph_name: str, run_id: str, now_ms: int) -> dict[str, Any]:
    """Run bounded graph-backed AND/OR discovery; this returns conditional plans, never dispatches."""
    store, graph = _store_graph(graph_name)
    try:
        rows = result_rows(graph.ro_query(load_query("Q15_run_goal"), {"runId": run_id}))
        if not rows:
            raise ValueError("run or goal not found in the requested project graph")
        row = rows[0]
        goal = Goal(id=row["goalId"], output_type=row["outputType"], order_id=row["orderId"],
            warehouse_id=row["warehouseId"], destination_zone=row["destinationZone"],
            weight_kg=float(row["weightKg"]), max_cost_units=int(row["maxCostUnits"]),
            cutoff_at=int(row["cutoffAt"]))
        planner = ConditionalPlanner(store, graph_name, run_id, goal, int(now_ms),
                                     int(row["catalogRevision"]))
        result = planner.discover()
        return {"status": result["status"], "runId": run_id,
            "basedOnRevision": row["revision"], "goal": result.get("goal"),
            "steps": result.get("steps", []), "preservedArtifacts": result.get("preservedArtifacts", []),
            "rejected": result.get("rejected", []), "blockers": result.get("blockers", []),
            "exploredExpansions": result.get("exploredExpansions"),
            "queryEvidence": [{"queryId": e["queryId"], "sha256": e["sha256"],
                               "rowCount": e["rowCount"], "elapsedMs": e["elapsedMs"]}
                              for e in result.get("evidence", [])],
            "executionWarning": "Conditional plan only. Provider actions require the guarded executor and current preflight."}
    finally:
        store.close()


@mcp.tool()
def read_execution_evidence(graph_name: str, run_id: str) -> dict[str, Any]:
    """Read durable intent, attempt, receipt, event and Booking projection evidence."""
    store, graph = _store_graph(graph_name)
    try:
        rows = result_rows(graph.ro_query(load_query("Q13_read_projection"), {"runId": run_id}))
        if not rows or rows[0].get("runId") is None:
            raise ValueError("run not found in the requested project graph")
        events = sorted({(r.get("eventSequence"), r.get("eventType"))
                         for r in rows if r.get("eventSequence") is not None})
        return {"runId": rows[0]["runId"], "runStatus": rows[0]["runStatus"],
            "revision": rows[0]["revision"], "effectState": rows[0].get("effectState"),
            "intents": sorted({(r.get("intentId"), r.get("intentStatus"), r.get("operationKey"))
                               for r in rows if r.get("intentId")}),
            "attempts": sorted({(r.get("attemptId"), r.get("attemptOutcome"))
                                for r in rows if r.get("attemptId")}),
            "receipts": sorted({(r.get("receiptId"), r.get("providerRecordId"))
                                for r in rows if r.get("receiptId")}),
            "artifacts": sorted({r.get("artifactId") for r in rows if r.get("artifactId")}),
            "events": events, "source": "FalkorDB Q13_read_projection"}
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewire MCP server backed by FalkorDB")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        _require_loopback(args.host)
        mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
