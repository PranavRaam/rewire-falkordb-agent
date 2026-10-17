# 5. Backend, persistence and API

## Architecture

~~~mermaid
flowchart TB
  UI[Recovery control room] --> API[FastAPI: commands and snapshots]
  API --> CO[Single coordinator and execution gates]
  CO --> AG[Agent loop]
  AG --> MCP[Typed MCP tools]
  MCP --> PL[Planner and graph repository]
  PL --> F[(FalkorDB)]
  MCP --> CO
  CO --> AD[Registered provider adapters]
  AD --> SIM[Separate provider simulator]
  SIM --> WORLD[(Provider world ledger)]
  F --> EVT[Durable event reader]
  EVT --> UI
  EVAL[Evaluation runner] --> API
  EVAL --> WORLD
~~~

The graph contains what the agent has observed. The provider ledger contains what actually happened. The evaluator can compare them; the agent cannot secretly read the world ledger.

## Planned repository layout

~~~text
track 01/
  README.md
  docs/                         # this blueprint
  apps/web/src/
    features/runs/
    features/graph/
    features/decisions/
    features/replay/
    components/
  services/api/rewire/
    api/                        # request validation and routes
    domain/                     # typed states and contracts
    graph/queries/              # named parameterized Cypher
    planner/                    # bounded search, binding, scoring
    execution/                  # intent and reconciliation protocol
    agents/                     # model adapter and agent loop
    mcp/                        # registered tool boundary
    adapters/                   # inventory/carrier/reporting adapters
  services/simulator/
    providers/
    faults/
    world_store/
  graph/udfs/
  fixtures/catalogs/
  fixtures/scenarios/
  evals/cases/
  evals/baselines/
  evals/results/
  infra/
  scripts/
~~~

Implemented folders currently include `src/rewire/` for Phase 1 graph discovery and `services/simulator/rewire_simulator/` for the independent Phase 2 provider world. The API, agent, MCP, execution protocol, frontend, evaluator suite and deployment folders remain planned; this layout is not a claim that those components exist.

## API contract

| Method and route | Behavior |
| --- | --- |
| POST /api/runs | Create isolated run from an allowed scenario and typed goal |
| GET /api/runs/{id} | Current snapshot, application revision, event cursor and mode |
| POST /api/runs/{id}/start | Idempotently start the agent |
| POST /api/runs/{id}/plans | Request graph-derived candidates at a revision |
| POST /api/runs/{id}/execute | Execute selected valid plan under a client request key |
| POST /api/runs/{id}/reconcile | Request bounded reconciliation of an unresolved intent |
| POST /api/runs/{id}/pause | Stop scheduling new mutations; preserve in-flight tracking |
| GET /api/runs/{id}/graph | Filtered view of capability or execution subgraph |
| GET /api/runs/{id}/decisions/{decisionId} | Selection, rejected alternatives and evidence |
| GET /api/runs/{id}/events?after={sequence} | Ordered SSE stream |
| POST /api/runs/{id}/snapshots | Create non-executing graph snapshot |
| POST /api/demo/runs/{id}/faults | Demo-only fault configuration, isolated from agent tools |
| GET /api/health | Liveness without secrets |
| GET /api/ready | Graph, configuration and compatible dependency readiness |

Use typed JSON requests and responses generated into frontend types. Stable error codes include STALE_REVISION, INCOMPATIBLE_BINDING, EFFECT_UNRESOLVED, SEARCH_LIMIT_REACHED, GRAPH_UNAVAILABLE and PROVIDER_UNAVAILABLE. Errors include a correlation ID and user-readable next step.

Execution requests carry plan ID, expected revision and client request ID. Provider payloads are assembled by the backend from validated bindings, not accepted as arbitrary browser input.

## Domain result shape

~~~json
{
  "runId": "run-104",
  "revision": 17,
  "status": "PAUSED_UNKNOWN",
  "mode": "live",
  "goal": {"id": "shipment:O-104", "satisfied": false},
  "unresolvedEffects": [
    {"intentId": "intent-9", "state": "UNKNOWN", "nextAllowedAction": "reconcile"}
  ],
  "lastEventSequence": 42
}
~~~

This is an illustrative API example, not a recorded run.

## Events and reconnection

Each event contains runId, sequence, type, timestamp, revision and a versioned payload. Event types include run.started, plan.proposed, plan.rejected, step.started, artifact.observed, effect.unknown, effect.confirmed, run.blocked and run.succeeded.

Write the event with its corresponding graph state transition where supported by a verified single-query mutation. Serialize coordinator transitions and enforce expected revisions. Do not emit a success event before the corresponding state has been accepted.

The client first obtains a snapshot and cursor, then consumes events after that cursor. Reconnect uses the last processed sequence and deduplicates by run ID plus sequence. If retained history is unavailable, fetch a new snapshot rather than silently skipping updates.

## Durability and restart

The existing compose file uses a named volume and an unpinned image. In Phase 1, determine the actual persistence configuration and choose the required settings for durable intents. Document any acknowledged-write loss window. A container remaining alive is not a durability test.

On app restart, enumerate project-owned unfinished runs, recover IN_FLIGHT/PREPARED/UNKNOWN intents through provider status, and then resume scheduling. Never reconstruct completion from a cached UI state.

No database reconfiguration or graph deletion should affect unrelated projects. Reset creates a fresh run namespace. Cleanup only targets explicit project-owned IDs after their retention period.

## Operational boundaries

- One coordinator process initially; concurrency within it is bounded and guarded.
- Expose the database only on the intended private/container network or local interface.
- Keep API/model secrets in environment configuration and out of receipts and event payloads.
- Run and graph authorization is server-side; separate graph names alone are not access control.
- Do not let an LLM submit arbitrary Cypher, load UDF code or choose filesystem paths.
- Cap query time, search expansions, model/tool calls and simulator payload sizes.
- A graph outage blocks new actions; do not silently switch to a flat in-memory fallback.
- HTTP deployment needs a host that supports the backend, database connectivity and streaming. A static website host alone cannot run this architecture.

## What to record for diagnosis

Correlation IDs connect user requests, agent tool calls, graph queries, intents and provider calls. Capture query latency, result count, search expansions, model usage, provider latency and validation failures. Redact secrets and avoid unnecessary raw payload retention.

Store environment and version metadata with every evaluation. Report graph query time, search time, model time and provider time separately so a fast database query is not presented as a fast end-to-end agent.
