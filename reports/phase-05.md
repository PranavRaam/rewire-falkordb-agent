# Phase 5 — Control room verification

**Status:** PASS on 17 October 2026.

## Delivered surface

- A project overview that introduces the problem, graph role and live scenarios before entering the product.
- A control room with graph-derived recovery steps, selected-record inspection, exact Cypher evidence, ordered server-sent events, replay and independent provider audit.
- A bounded approval flow that exposes either local-model MCP execution or direct deterministic MCP execution only after a plan digest is available.
- A mobile layout that changes the recovery map to its accessible ordered-step representation.

The overview labels its fixed graph image as an illustration. It does not present synthetic events, receipts or booking counts as if a run has already occurred.

## Reproduction

Build the client and start the local host from the repository root:

~~~powershell
cd apps\web
npm ci
npm run build
cd ..\..
.\run-ui.ps1
~~~

The local site is `http://127.0.0.1:8787`. The verifier starts isolated runs through the HTTP API and needs the local FalkorDB instance:

~~~powershell
python scripts/verify_control_room.py
~~~

## Gate checks

The saved result in [control-room-verification.json](phase-05/control-room-verification.json) confirms:

1. Cross-site form mutations are rejected and a plan cannot execute without its approval digest.
2. Carrier B and the catalog-changed Carrier D each produce four durable receipts and one independent booking.
3. The UI receives exact graph query rows for planned steps, artifacts and events.
4. The SSE snapshot and event stream are ordered and durable.
5. A response lost after the booking commit reconciles by operation key instead of causing another booking.
6. Repeating the same approval has no duplicate external effect; expired reservations block execution.
7. Evidence export contains the graph reasoning and execution evidence.

## Scope limit

This verifies a local, single-coordinator demonstration using actual FalkorDB and a synthetic external provider backed by SQLite. The independent provider audit is intentionally absent from agent-facing endpoints. The model-driven presentation path has separate Phase 4 verification.
