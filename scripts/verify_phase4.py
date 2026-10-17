"""Live Phase 4 gate: local/remote model tool call over a fresh FalkorDB graph."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rewire.agent import run_agent  # noqa: E402
from rewire.fixtures import BASE_MS  # noqa: E402
from rewire.phase1 import run_phase1  # noqa: E402

REPORT_PATH = ROOT / "reports" / "phase-04" / "verification.json"


def main() -> int:
    report: dict = {
        "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        "status": "FAILED",
        "checks": {},
    }
    try:
        seeded = run_phase1("base")
        result = run_agent(
            "Inspect the recovery plan and explain what is feasible, what it preserves, "
            "and why the rejected carriers are unsuitable.",
            seeded["graphName"], seeded["runId"], BASE_MS,
        )
        trace = result.get("toolTrace", [])
        inspect = next((item for item in trace if item.get("tool") == "inspect_run"), None)
        discovery = next((item for item in trace if item.get("tool") == "discover_recovery"), None)
        facts = result.get("verifiedFacts") or {}
        rejected_codes = {item.get("reasonCode") for item in facts.get("rejected", [])}
        checks = {
            "liveModelToolCall": bool(inspect and inspect.get("status") == "EXECUTED"),
            "falkordbRecoveryDiscovery": bool(discovery and discovery.get("status") in
                ("EXECUTED", "POLICY_REQUIRED") and
                (discovery.get("result") or {}).get("status") == "STRUCTURALLY_VALID"),
            "verifiedSummaryReturned": result.get("status") == "COMPLETE" and bool(result.get("final")),
            "fourStepCandidate": len(facts.get("steps", [])) == 4,
            "allStepsRemainConditional": bool(facts.get("steps")) and all(
                step.get("status") == "CONDITIONAL" for step in facts.get("steps", [])),
            "reservationPreserved": "artifact:reservation:R81" in facts.get("preservedArtifacts", []),
            "carrierRejectionsExplained": {
                "TOOL_DISABLED", "PACKAGE_WEIGHT_EXCEEDS_TOOL_LIMIT"
            }.issubset(rejected_codes),
            "noProviderMutationToolExposed": all(
                item.get("tool") in {"inspect_run", "discover_recovery", "read_execution_evidence"}
                for item in trace
            ),
        }
        report.update({
            "status": "PASS" if all(checks.values()) else "FAILED",
            "provider": result.get("provider"),
            "model": result.get("model"),
            "graphName": seeded["graphName"],
            "runId": seeded["runId"],
            "modelResponseStatus": result.get("modelResponseStatus"),
            "modelFinishReason": result.get("modelFinishReason"),
            "answerMode": result.get("answerMode"),
            "toolTracePath": result.get("tracePath"),
            "summary": result.get("final"),
            "checks": checks,
        })
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
