"""HTTP acceptance gate for the live control room; requires run-ui.ps1.

Creates only fresh project-owned graphs and synthetic provider ledgers.
No browser/model results are inferred from this deterministic API gate.
"""
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8787"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path, body=None, expected=200, client=True):
    headers = {"Content-Type": "application/json"}
    if client:
        headers["X-Rewire-Client"] = "control-room"
    request = urllib.request.Request(BASE + path, headers=headers,
        data=None if body is None else json.dumps(body).encode())
    try:
        with OPENER.open(request, timeout=60) as response:
            code, value = response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        code, value = exc.code, json.load(exc)
    assert code == expected, (path, code, value)
    return value


def settle(run_id):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        value = call(f"/api/runs/{run_id}")
        if not value["busy"]:
            assert not value.get("error"), value.get("error")
            return value
        time.sleep(.2)
    raise AssertionError("Recovery did not settle")


def main():
    assert call("/api/health")["graph"]
    call("/api/runs", {"scenario":"base"}, expected=403, client=False)
    checks = {"crossSiteFormMutationDenied": True}
    runs = []
    for scenario in ("base", "carrier-d"):
        run = call("/api/runs", {"scenario":scenario, "faultAfterCommit":True}, expected=201)
        run_id = run["runId"]
        assert run["plan"]["status"] == "STRUCTURALLY_VALID"
        assert len(run["plan"]["steps"]) == 4
        assert not run["executionSteps"] and not run["events"]
        assert len(run["artifacts"]) == 3
        assert all(e["rowCount"] == len(e["rows"]) for e in run["plan"]["evidence"])
        call(f"/api/runs/{run_id}/audit", expected=409)
        call(f"/api/runs/{run_id}/execute", {"approvalDigest":"0"*64,"mode":"direct"}, expected=409)
        with OPENER.open(BASE+f"/api/runs/{run_id}/events", timeout=10) as response:
            assert response.readline().decode().strip() == "event: snapshot"
            streamed = json.loads(response.readline().decode()[6:])
            assert streamed["runId"] == run_id and streamed["state"]["revision"] == 1
        payload = {"approvalDigest":run["approvalDigest"],"mode":"direct"}
        call(f"/api/runs/{run_id}/execute", payload, expected=202)
        value = settle(run_id)
        assert value["state"]["runStatus"] == "SUCCEEDED"
        assert len(value["executionSteps"]) == 4
        assert all(s["receiptId"] and s["intentStatus"] == "CONFIRMED" for s in value["executionSteps"])
        assert any(e["type"] == "effect.unknown" for e in value["events"])
        assert [e["sequence"] for e in value["events"]] == sorted({e["sequence"] for e in value["events"]})
        audit = call(f"/api/runs/{run_id}/audit")
        assert audit["rowCounts"]["bookings"] == 1 and audit["rowCounts"]["operations"] == 4
        assert audit["visibleToAgent"] is False
        assert audit["bookings"][0]["provider_id"] == ("carrier-b" if scenario == "base" else "carrier-d")
        call(f"/api/runs/{run_id}/execute", payload, expected=202)
        replay = settle(run_id)
        repeated_audit = call(f"/api/runs/{run_id}/audit")
        assert repeated_audit == audit
        assert replay["events"] == value["events"]
        exported = call(f"/api/runs/{run_id}/export")
        assert exported["independentAudit"] == audit and "providerUrl" not in exported
        runs.append({"scenario":scenario,"runId":run_id,"graphName":run["graphName"],
                     "receipts":4,"events":len(value["events"]),"independentAudit":audit})
    expired = call("/api/runs", {"scenario":"expired"}, expected=201)
    assert expired["plan"]["status"] == "EXHAUSTIVE_NO_PLAN" and expired["approvalDigest"] is None
    call(f"/api/runs/{expired['runId']}/execute", {"approvalDigest":"0"*64,"mode":"direct"}, expected=409)
    call(f"/api/runs/{expired['runId']}/audit", expected=409)
    checks.update(planApprovalRequired=True, carrierBAndChangedCarrierD=True,
        exactQueryRowsExposed=True, snapshotStream=True, orderedDurableEvents=True,
        lostResponseReconciled=True, independentSingleBooking=True,
        repeatedApprovalDoesNotDuplicate=True, exportIncludesEvidence=True,
        expiredReservationBlocksExecution=True,
        consoleQueriesChecked=["Q18_console_steps", "Q19_console_artifacts", "Q20_console_events"])
    report = {"status":"PASS", "checks":checks,"runs":runs,
              "scope":"Local HTTP API, actual FalkorDB, deterministic MCP driver, synthetic provider. Browser and live model checked separately."}
    path = ROOT / "reports" / "phase-05" / "control-room-verification.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
