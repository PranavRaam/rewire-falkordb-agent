# Rewire Phase 1 — implementation and evidence

**Status: core graph discovery and the Phase 1 acceptance suite passed against local FalkorDB.** The acceptance run covers cycle and depth termination, graph isolation, outage fail-closed behavior, renamed/permuted imports, importer validation, and large query results. Evidence is saved in [acceptance-verification.json](phase-01/acceptance-verification.json). No UI, live LLM, provider mutation, booking, or shipment-completion claim is part of Phase 1.

## What Phase 1 now does

The CLI creates a fresh project-owned FalkorDB graph, installs ID indexes and constraints, loads a deterministic synthetic catalog and run, then queries connected tool contracts and artifacts. A bounded Python AND/OR planner expands the graph query results into a conditional plan. FalkorDB is the source of producer, required-slot, artifact-binding, schema/status/version/expiry, and dependency facts. Python owns the bounded search and cross-result reasoning; this is not represented as a built-in FalkorDB algorithm.

The base plan is:

1. `carrier-b-pickup` consumes the observed W7 warehouse.
2. `carrier-b-quote` consumes O-104 and the future Pickup output.
3. `carrier-b-label` consumes O-104 and the future Quote output.
4. `carrier-b-dispatch` consumes the future Label, Pickup and Quote outputs plus the observed R81 reservation.

All four steps remain `CONDITIONAL`. In particular, no quote price is asserted before a quote action runs, and no booking exists in this phase. The planner preserves the observed Order, W7 and R81 artifacts. It rejects Carrier A using its `enabled=false` catalog fact and Carrier C using `maxWeightKg=5 < requestedWeightKg=8`.

## Verified environment

| Component | Observed value |
| --- | --- |
| FalkorDB module | 4.22.1 (`ver=42201`) |
| Docker image digest | `sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a7` |
| Official Python client | `FalkorDB==1.8.0` |
| Python | CPython 3.10.0 |
| Local endpoint | `127.0.0.1:6379` |

Schema installation created 15 ID range indexes and 30 UNIQUE/MANDATORY ID constraints. Indexes and constraints were checked in `db.indexes()` and `db.constraints()` until their status was `OPERATIONAL`. The client’s `PENDING` return is preserved as the creation acknowledgement; it is not misreported as the final status. A live failed write confirmed duplicate Artifact IDs are rejected, and another confirmed missing Artifact IDs are rejected.

## Runtime checks completed

| Check | Result and evidence |
| --- | --- |
| Base producer discovery | **Pass.** FalkorDB-backed discovery selected the four B steps. [Latest base report](phase-01/runs/20261017T045353Z-6ee315dab90f.json) |
| Rejection explanations | **Pass.** A disabled; C rejected for the declared 5 kg limit against the 8 kg goal, with Q01R facts. |
| Required input preservation | **Pass.** The four dispatch input slots each have a binding; R81 is retained. Quote and Label are represented as planned outputs, not observed artifacts. |
| Exact version/schema/expiry | **Pass.** Q03 accepted an exact version, rejected a mismatched version and schema, and rejected the reservation at its exact `expiresAt`. |
| Order/warehouse scope | **Pass.** Synthetic O-999 and W9 reservations were visible to the diagnostic query but could not bind to O-104/W7. |
| Q02 optional/missing slot behavior | **Pass.** Removing the quote producer led to `EXHAUSTIVE_NO_PLAN` with an explicit unsatisfied required slot. [Missing-input report](phase-01/runs/20261017T045256Z-5c87f87566d0.json) |
| Expiration boundary in planner | **Pass.** At R81’s exact expiry millisecond the planner no longer preserves it and finds no complete plan. [Expiry report](phase-01/runs/20261017T045301Z-c93390b1a0e0.json) |
| Catalog generality | **Pass.** B disabled and a distinct D prerequisite chain added; the planner selected D without planner-code changes. [Carrier D report](phase-01/runs/20261017T045251Z-f8eb5e185895.json) |
| Q04 dependency direction | **Pass.** Q04 returned the downstream dependent, excluding the prerequisite and unrelated step. |
| FalkorDB constraints | **Pass.** Duplicate and missing `Artifact.id` writes were rejected on the live graph. |
| Procedure inventory | **Available.** Q00 observed registered procedures including AStar, BFS, HarmonicCentrality, maxFlow, WCC, PageRank, and CCH query support. Registration alone is not treated as semantic verification or a product dependency. |

Every saved query evidence item includes query text, SHA-256, parameters, result rows, elapsed time, source documentation URL, and execution count. The latest base report also includes the image digest and client/server versions. Query-level status is recorded separately for documentation, availability, execution, semantic checks, and integration checks.

## Commands and setup

The working run command is `.\run.ps1 plan --scenario base` from this directory, with the local FalkorDB container running. For a clean environment, create `.venv` with Python 3.10 and install `requirements.lock`; `run.ps1` prefers that environment when the FalkorDB client imports successfully, then falls back to the active `python` command. `.env.example` contains only local connection defaults; copy it to `.env` and set credentials only if your local database requires them. `run.ps1` reads a small allow-list of connection keys and passes them to the Python process. It sets `PYTHONPATH=src`, so the CLI can run from the source checkout without an editable package install.

Other verified scenarios:

~~~powershell
.\run.ps1 plan --scenario carrier-d
.\run.ps1 plan --scenario missing-input
.\run.ps1 plan --scenario expired
~~~

`python -m compileall -q src` completed. No external service/API or real customer data is used. `requirements.lock` pins the Python dependency versions observed for this run.

The local setup started from the existing `falkordb-local` Docker Compose service. Phase 1 connected to its loopback endpoint and created only namespaced `rewire_phase1_*` graphs. The working commands were `docker compose up -d` in the FalkorDB project, then `.\run.ps1 plan --scenario ...` here.

## FalkorDB documentation checked

- [Cypher MATCH](https://docs.falkordb.com/cypher/match), [OPTIONAL MATCH](https://docs.falkordb.com/cypher/optional-match), and [WITH](https://docs.falkordb.com/cypher/with) for query composition and null-preserving slot matching.
- [Graph query command](https://docs.falkordb.com/commands/graph.query) for parameter binding through the official client.
- [Range indexes](https://docs.falkordb.com/cypher/indexing/range-index) and [constraint creation](https://docs.falkordb.com/commands/graph.constraint-create) for schema installation and operational-status checks.
- [Procedures](https://docs.falkordb.com/cypher/procedures) for local capability inventory. This inventory is not a semantic algorithm benchmark.

## Files added for the implementation

- `src/rewire/domain.py` — typed goal, artifact, slot and tool contracts.
- `src/rewire/fixtures.py` — reproducible base, D, missing-input and expiry fixtures.
- `src/rewire/graph/store.py` — official client adapter, schema/index/constraint installation, importer checks and evidence capture.
- `src/rewire/graph/queries/` — named Q00–Q04 and diagnostic Q01R/Q02R Cypher files.
- `src/rewire/planner/engine.py` — bounded Python AND/OR planner.
- `src/rewire/phase1.py`, `src/rewire/cli.py`, `run.ps1` — execution, reports and CLI.
- `reports/phase-01/created-graphs.json` — explicit registry of Phase 1 graph names, statuses and reports.
- `reports/phase-01/runs/` — full machine-readable run and query evidence. Failed attempts are retained and clearly marked; no graph was globally flushed or deleted.

## Phase 1 acceptance gates

All six acceptance areas passed on 17 October 2026:

- A cyclic catalog terminates as `EXHAUSTIVE_NO_PLAN`; the depth fixture terminates as `SEARCH_LIMIT_REACHED`.
- Same-ID graphs return their own distinct artifact status when queried separately.
- A closed database port raises a connection error; no memory planner fallback runs.
- Renamed IDs and reversed node import order preserve the same plan shape.
- Corrupt relationship endpoints, duplicate edges, schema conflicts, and unsupported slot cardinality are rejected before graph writes.
- Q01 returned all 2,020 producer rows. A separate bounded-search probe reported its configured test limit; production remains bounded at 2,000 expansions.

The importer now validates relationship endpoints and duplicate edges as part of its pre-write validation. The machine-readable evidence lists each check and result.

## Exact boundary

Phase 1 is closed for the tested synthetic model and local FalkorDB version. The results do not establish correctness for arbitrary imported datasets or larger production graphs.
