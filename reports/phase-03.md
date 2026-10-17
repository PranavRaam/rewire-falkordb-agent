# Phase 3 — Execution and reconciliation evidence

**Status: PASS for the scoped simulator-backed execution path.** Verified 17 October 2026 against local FalkorDB and an isolated temporary SQLite provider world.

The gate used a fresh project-owned `rewire_phase1_*` graph, simulated carrier B API, and synthetic shipment O-104. It first materialized public simulator observations for pickup, quote and label, selected a dispatch plan, and bound the existing reservation R81 plus the three new artifacts. FalkorDB preflight returned all four required slots. The application checked run membership, exact artifact version, type/schema, status, and expiration before authorizing dispatch.

The coordinator rejected a stale graph revision. It then persisted a stable operation key, canonical payload hash, PREPARED intent and event before transitioning to IN_FLIGHT. The provider committed the booking and deliberately dropped the first response. The coordinator recorded UNKNOWN, and the unresolved logical effect remained claimed. A second provider intent was denied. A newly constructed coordinator recovered the original operation key and intent from FalkorDB, queried provider status, and verified the returned order, reservation, pickup, quote, label, provider, status and record identity. The receipt was recorded against the expected payload hash. The coordinator was reconstructed after receipt commit and resumed artifact projection; it was reconstructed again after projection commit and returned the same confirmed artifact on retry without another provider call.

The evaluator-side simulator audit found exactly one booking, one pickup, one quote, one label and four operation records. Ordered event sequence 2–8 was contiguous. Full machine-readable evidence, including generated graph/run IDs and booking IDs, is in [verification.json](phase-03/verification.json).

## Verified checks

- All required artifact slots were returned and semantically checked before authorization.
- Stale revision was denied.
- Caller retry of the intent claim returned the original intent.
- The intent/effect claim preceded provider dispatch.
- Post-commit response loss remained UNKNOWN until reconciliation.
- The logical effect fence blocked a replacement provider intent.
- Coordinator reconstruction recovered the durable intent and original operation key.
- Provider status confirmed the intended booking and payload identity.
- Receipt and Booking artifact were persisted to FalkorDB.
- Booking projection retry was idempotent.
- A never-submitted simulator operation returned 404; Q11 denied a non-authoritative absence claim and released the effect only when the adapter supplied the verified authoritative flag.
- A PREPARED intent was recovered through status lookup after coordinator reconstruction; it was not dispatched again, and authoritative absence released its effect.
- Provider audit showed exactly one booking.

## Limits

This verifies a single coordinator process and the synthetic adapter's synchronous database commit, idempotency-key and status-lookup contract. It does not establish distributed fencing across multiple coordinator processes, arbitrary provider semantics, or universal exactly-once execution. Q11's authoritative `NO_EFFECT` semantics are verified only for the simulator's never-submitted key. Do not use that transition for another provider unless it guarantees a status absence is authoritative after a documented visibility window. The interface/demo and live LLM/MCP agent remain later phases.
