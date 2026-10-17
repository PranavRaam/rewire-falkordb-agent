"""Phase 1 CLI."""

from __future__ import annotations

import argparse
import json
import sys

from rewire.phase1 import run_phase1


def main() -> None:
    parser = argparse.ArgumentParser(prog="rewire")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="seed a new owned graph and discover a conditional plan")
    plan.add_argument("--scenario", choices=("base", "carrier-d", "missing-input", "expired"), default="base")
    plan.add_argument("--now-ms", type=int, default=None,
                      help="override the synthetic scenario clock for expiry checks")
    agent = commands.add_parser("agent", help="run the bounded model agent over MCP-style graph tools")
    agent.add_argument("--graph", required=True)
    agent.add_argument("--run", required=True)
    agent.add_argument("--now-ms", required=True, type=int)
    agent.add_argument("--request", required=True)
    mcp = commands.add_parser("mcp", help="serve typed graph tools over MCP")
    mcp.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "agent":
        from rewire.agent import run_agent
        try:
            print(json.dumps(run_agent(args.request, args.graph, args.run, args.now_ms), indent=2))
        except Exception as exc:
            print(f"Agent failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return
    if args.command == "mcp":
        from rewire.mcp_server import mcp, _require_loopback
        if args.transport == "stdio":
            mcp.run(transport="stdio")
        else:
            _require_loopback(args.host)
            mcp.run(transport="streamable-http", host=args.host, port=args.port)
        return
    try:
        result = run_phase1(args.scenario, args.now_ms)
    except Exception as exc:
        print(f"Phase 1 failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    plan_result = result.get("plan", {})
    print(json.dumps({
        "status": result["status"],
        "scenario": result["scenario"],
        "graphName": result["graphName"],
        "runId": result["runId"],
        "planStatus": plan_result.get("status"),
        "steps": [step["toolId"] for step in plan_result.get("steps", [])],
        "preservedArtifacts": plan_result.get("preservedArtifacts", []),
        "rejected": [item.get("reasonCode") for item in plan_result.get("rejected", [])],
        "boundaryChecks": [{"check": item["check"], "passed": item["passed"]}
                           for item in result.get("boundaryChecks", [])],
        "reportPath": result.get("reportPath"),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
