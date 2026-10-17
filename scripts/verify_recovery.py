"""Exercise real MCP actions and independently audit the synthetic provider world."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "services" / "simulator")]
from rewire.agent import _call_mcp_tool, run_agent
from rewire.fixtures import BASE_MS
from rewire.phase1 import run_phase1
from rewire.mcp_server import authorize_recovery
from rewire.recovery import preview_recovery, SimulatorClient
from rewire.graph.store import GraphStore
from rewire_simulator.store import ProviderWorld, FaultController


def verify(scenario="base", live=False):
    seed = run_phase1(scenario)
    graph, run = seed["graphName"], seed["runId"]
    args = {"graph_name":graph,"run_id":run}
    checks = {}
    denied = _call_mcp_tool("execute_approved_recovery", args)
    assert denied.get("status") == "REJECTED", denied
    checks["unapprovedMcpActionDenied"] = True
    preview = preview_recovery(graph, run, BASE_MS)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="rewire-recovery-") as temp:
        db = Path(temp) / "world.sqlite3"
        env = {**os.environ,"PYTHONPATH":str(ROOT / "services" / "simulator")}
        proc = subprocess.Popen([sys.executable,"-m","rewire_simulator","--port",str(port),
            "--db",str(db),"--now-ms",str(BASE_MS),"--fault-after-commit","booking"],
            env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic()+10
            while True:
                try:
                    SimulatorClient(base).now()
                    break
                except OSError:
                    if time.monotonic()>deadline: raise
                    time.sleep(.1)
            with authorize_recovery(graph,run,"invalid-digest",base):
                denied = _call_mcp_tool("execute_approved_recovery",args)
                assert denied.get("status") == "REJECTED", denied
                checks["invalidApprovalDenied"] = True
            if live:
                result = run_agent("Execute the approved recovery and verify the booking evidence.",
                    graph,run,BASE_MS,approved_digest=preview["approvalDigest"],provider_url=base,
                    max_tool_rounds=10)
                if result["status"] != "COMPLETE":
                    raise AssertionError(json.dumps(result))
                checks["liveModelSelectedAction"] = any(x.get("tool")=="execute_approved_recovery"
                    and x["status"]=="EXECUTED" for x in result["toolTrace"])
            else:
                with authorize_recovery(graph,run,preview["approvalDigest"],base):
                    result = _call_mcp_tool("execute_approved_recovery",args)
                    assert result["status"] == "SUCCEEDED", result
            # New session/client reconstructs intent and receipt state from FalkorDB.
            with authorize_recovery(graph,run,preview["approvalDigest"],base):
                replay = _call_mcp_tool("execute_approved_recovery",args)
                assert replay["status"] == "SUCCEEDED", replay
            evidence = _call_mcp_tool("read_execution_evidence",args)
            assert evidence["runStatus"] == "SUCCEEDED", evidence
            assert len(evidence["receipts"]) == 4, evidence
            checks["allFourStepsHaveReceipts"] = True
            checks["reconstructedSessionReplay"] = True
            assert any(event[1] == "effect.unknown" for event in evidence["events"]), evidence
            checks["lostBookingResponseReconciled"] = True
        finally:
            proc.terminate()
            proc.wait(timeout=5)
        audit = ProviderWorld(db,BASE_MS,FaultController()).evaluator_audit()
        assert audit["rowCounts"]["bookings"] == 1, audit
        assert audit["rowCounts"]["operations"] == 4, audit
        checks["independentAuditExactlyOneBooking"] = True
        checks["noDuplicatePrerequisites"] = True
    return {"scenario":scenario,"checks":checks,"graphName":graph,"audit":audit}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live",action="store_true")
    args = parser.parse_args()
    report = {"status":"PASS","runs":[verify(name,args.live) for name in ("base","carrier-d")]}
    target = ROOT / "reports" / "phase-04" / "recovery-verification.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
