# Rewire — Track 01 implementation blueprint

**Decision: build Rewire.** Its graph discovery, execution coordinator, and recovery agent are implemented and checked against local FalkorDB and a synthetic provider world. See the [Phase 1 evidence](reports/phase-01.md) and [Phase 4 recovery verification](reports/phase-04/recovery-verification.json).

**Start with [the revised judge's-eye plan](docs/10-revised-strategy.md), then [the query contract](docs/11-query-contract.md). Phase 1 acceptance, Phase 2 simulation, Phase 3 reconciliation, Phase 4 model-backed recovery, and Phase 5 control-room gates have passed for the documented synthetic fixtures.**

Assumptions: one solo builder using an LLM coding assistant; the specified Python/FastAPI/FalkorDB/React/MCP stack; no scope reduction based on estimated hours. Every retained feature must have a visible demonstration, UI or README payoff. Documentation review is evidence of syntax and intended semantics, not proof that our composed queries work.

Rewire is an agent that repairs interrupted tool workflows. It uses FalkorDB to discover alternative ways to finish a goal, preserve work that is still valid, and establish what actually happened before taking another irreversible action.

**The pitch:** “When a workflow breaks halfway through, Rewire finds a valid way forward—and proves which actions it took.”

Planning date: 17 October 2026. This blueprint uses dependency and quality gates rather than a compressed timetable. The event deadline still applies to an actual submission; extending this plan does not extend the competition window.

## Why I choose this project

Rewire has a particularly clear demonstration: a shipment workflow fails, the agent discovers a different chain of tools, and a lost response forces it to distinguish a missing answer from a missing shipment. A judge can change the failure and watch the decision change.

Compared with SwarmSwitch, I prefer Rewire because it can establish a concrete result with a smaller, more inspectable world model. Its difficulty is substantive: dependencies, compatible inputs, incomplete observations, and effects that may already have occurred. This is a design judgment, not a prediction of ranking or an assertion that workflow recovery is a new research field.

## Read in this order

1. [The product and complete worked examples](docs/01-product-and-worked-examples.md)
2. [Step-by-step implementation phases](docs/02-implementation-phases.md)
3. [Graph model and FalkorDB capabilities](docs/03-graph-model-and-falkordb.md)
4. [Planning algorithm and execution protocol](docs/04-planner-and-execution-protocol.md)
5. [Backend, persistence and API contracts](docs/05-backend-and-api.md)
6. [AI behavior and MCP tools](docs/06-ai-and-mcp.md)
7. [UI and interaction specification](docs/07-ui-and-interactions.md)
8. [Evaluation, demonstration and submission](docs/08-evaluation-and-demo.md)
9. [Research, capability verification and decisions](docs/09-research-and-decisions.md)
10. [Revised priorities, judge assessment, pitch and risks](docs/10-revised-strategy.md)
11. [Exact proposed Cypher, algorithm boundaries and verification contract](docs/11-query-contract.md)
12. [Paste-ready Phase 1 prompt only](prompts/phase-01.md)

Revision 2 authority: document 11 owns query IDs, concrete property contracts and verification requirements; document 10 owns priorities; document 2 owns phase numbering. Earlier conceptual examples are explanatory and do not override these contracts.

## What the finished demonstration must establish

- A real agent selects tools using connected capabilities and requirements stored in FalkorDB.
- The replacement workflow is discovered from contracts, not selected by a provider-specific fallback branch.
- Every required input is satisfied, including identities, versions, expiry and resource ownership.
- Tools actually change a durable synthetic provider environment.
- A response lost after a successful booking triggers reconciliation, not another booking.
- The UI explains accepted and rejected choices with query results and receipts.
- Measured comparisons show where the graph helps and where it does not.

## Direct fit for Track 01

| Track focus | Rewire evidence |
| --- | --- |
| Multi-hop reasoning | Goal → required artifact → producer tool → its prerequisites → available artifacts |
| Queries and algorithms as tools | Dependency expansion, affected-step traversal, compatibility checks and bounded plan search |
| MCP tool selection | The agent calls typed graph tools and then authorized provider tools |
| Actions based on the graph | Only a currently valid graph-backed plan can authorize a mutating tool call |
| Explainable results | Every action links to its inputs, decision, attempt and observed receipt |

These map directly to the organizer's [Track 01 description](https://www.wemakedevs.org/hackathons/falkordb#challenge). Persisting execution history supports the product; the submission's central claim remains graph-directed action.

## Chosen stack

| Layer | Choice and purpose |
| --- | --- |
| UI | React, TypeScript, Vite, React Flow; a recovery control room |
| Application | Python, FastAPI, Pydantic; one coordinator process initially |
| Operational graph | FalkorDB; contracts, artifacts, plans, intents, attempts, receipts and events |
| Agent interface | Official Python MCP SDK with bounded, typed tools |
| AI | Configurable provider adapter supporting tool calls and structured output |
| Synthetic external world | Separate simulator process with transactional SQLite provider records |
| Live transport | Durable events delivered through server-sent events |
| Packaging | Reproducible containers, pinned versions and documented local setup |

SQLite represents the systems being acted upon, such as an inventory provider. It does not store the planner's graph or select tools. Keeping provider truth separate from agent observations is necessary to demonstrate lost-response recovery honestly.

## Scope and ambition

The complete product includes a robust recovery core, a polished explanation interface, graph-native compatibility logic, measured retrieval and ingestion at scale, and optional route-cost acceleration when a real routing workload justifies it. “Maximum FalkorDB use” means that each feature has an observable job and an evaluation. A feature count is not a product advantage.

The intended competitive edge is the combination of a strong failure demonstration, inspectable graph reasoning, actual side effects, and unusually rigorous evidence. No architecture or UI can justify an 80% chance of winning without knowledge of the competing submissions and judging.

## Completion record

- [x] Choose the Track 01 project.
- [x] Create a separate Track 01 planning workspace.
- [x] Specify product behavior, architecture, phases, examples and evaluation.
- [x] Verify the used FalkorDB capabilities on the project image.
- [x] Implement the application, simulator and local control room.
- [ ] Run the evaluation and publish measured results.
- [ ] Produce submission materials.

Existing infrastructure remains in ../falkordb-local. Track 02 and the existing proposal website are separate projects. The phase plan creates no dependency on changing either one.

## Phase 1 implementation status

The current CLI installs a project-owned graph schema, seeds deterministic synthetic shipment/tool-contract data, queries FalkorDB for candidate producers and compatible inputs, and runs bounded AND/OR discovery in Python over those query results. Phase 1 does not call provider tools or claim a shipment completed.

From PowerShell with the local FalkorDB container running and the locked Python dependencies installed:

~~~powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
# Edit .env only if your local FalkorDB requires credentials.
.\run.ps1 plan --scenario base
.\run.ps1 plan --scenario carrier-d
.\run.ps1 plan --scenario missing-input
.\run.ps1 plan --scenario expired
~~~

Each command creates a fresh graph named `rewire_phase1_<run-id>` and saves full query evidence under `reports/phase-01/runs/`. The concise CLI output prints the graph name and report path. Graphs are retained for inspection; no existing graph is dropped or flushed.

### Phase 2 provider-world simulator

Phase 2 adds an independent loopback HTTP process backed by a local SQLite provider ledger. The graph remains the agent's observed state; provider truth is in the simulator database. The HTTP service has no evaluator-audit endpoint.

~~~powershell
.\run-simulator.ps1 --port 8765
~~~

Set up pickup, quote, label, and booking via `/v1/carriers/carrier-b/{pickup|quote|label|booking}`. Mutating calls require an `Idempotency-Key` header. To deliberately drop the first successful booking response after its SQLite transaction commits, start the simulator with `--fault-after-commit booking`. Query the operation by key at `/v1/carriers/carrier-b/operations/{key}`, then retry with the same key and payload. The script checks the after-commit loss, status lookup, exact idempotent replay, conflicting-payload rejection, and the hidden evaluator audit:

~~~powershell
python scripts/verify_phase2.py
~~~

The verifier starts and stops its own isolated simulator process and stores its temporary SQLite world under the system temp directory. It does not connect to, modify, or delete FalkorDB graphs.

The Phase 2 gate passed on 2026-10-17. Its saved evidence is [reports/phase-02.md](reports/phase-02.md) and [reports/phase-02/verification.json](reports/phase-02/verification.json).

### Phase 3 execution coordinator

Phase 3 connects selected-plan preflight, graph-persisted intents and attempts, the local provider simulator, restart reconciliation, receipts, and the final Booking artifact projection. Run the gate with `python scripts/verify_phase3.py` after FalkorDB is available. The script creates a fresh `rewire_phase1_*` graph and a temporary simulator database.

The verification passed on 2026-10-17. Evidence and known limits are documented in [reports/phase-03.md](reports/phase-03.md) and [reports/phase-03/verification.json](reports/phase-03/verification.json). The coordinator is intentionally single-process. Its guarantee relies on the simulator's documented idempotency and status lookup behavior; it does not claim exactly-once outcomes for arbitrary providers.

### Phase 4 live agent and MCP

The bounded model tool loop discovers its schemas through MCP and restricts graph/run scope and synthetic clock. Ordinary agent sessions receive read-only tools. A trusted host can approve one exact recovery snapshot by digest; only then is `execute_approved_recovery` exposed. Approval is never inferred from model prose. `recovery-preview --graph <graph> --run <run> --now-ms <fixture-time>` prints the plan and digest. Start the simulator on loopback with the same frozen time (`.\\run-simulator.ps1 --port 8091 --now-ms <fixture-time> --fault-after-commit booking`), then run the agent with `--approve-plan <digest> --provider-url http://127.0.0.1:8091`. Each prerequisite and final booking is revalidated against FalkorDB, has a durable intent before dispatch, uses a stable idempotency key, and is projected only after provider status proves the output. Ambiguous results stop for reconciliation rather than starting a second operation. `python scripts/verify_recovery.py` checks Carrier B and changed Carrier D graph plans and audits provider truth independently; `--live` additionally requires the configured model. This remains a single-coordinator-process synthetic-provider demonstration, not a distributed production executor.
The checked environment was FalkorDB module 4.22.1, official `FalkorDB` Python client 1.8.0, CPython 3.10.0, Docker image digest `sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a7`. Phase 1 acceptance is closed for the documented synthetic model; the detailed edge-case evidence is in [reports/phase-01/acceptance-verification.json](reports/phase-01/acceptance-verification.json).

### Phase 5 control room and project overview

The local web application opens on an incident launch surface, then moves into the live recovery control room. It exposes the graph-derived plan, recorded Cypher and results, bounded planner work, preserved artifacts, approval digest, MCP execution, durable event stream, replay, provider receipts and an independent provider-ledger audit. The UI currently demonstrates the fulfillment fixture; other domains require their own graph contracts, data and provider adapter.

From the repository root, with Docker FalkorDB and Ollama running when model execution is desired:

~~~powershell
cd apps\web
npm ci
npm run build
cd ..\..
.\run-ui.ps1
~~~

Open `http://127.0.0.1:8787`. Launch the lost-response incident to create a fresh FalkorDB graph and isolated provider ledger. Inspect the discovered plan and query evidence, approve the exact plan digest, choose the local-model MCP driver or direct deterministic MCP execution, then run the independent audit to verify the provider booking count. The HTTP gate can be rerun with:

~~~powershell
python scripts/verify_control_room.py
~~~

The 17 October 2026 gate passed against actual FalkorDB. It checked cross-site mutation rejection, required approval, both valid carrier paths, exact UI query outputs, SSE ordering, lost-response reconciliation, independent one-booking audits, repeat-approval idempotency, evidence export and expired-reservation blocking. See [the saved verification result](reports/phase-05/control-room-verification.json).
