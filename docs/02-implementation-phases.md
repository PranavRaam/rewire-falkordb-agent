# 2. Revised implementation roadmap

One solo builder, assisted by an LLM. Work advances through evidence gates, without hour-based scope limits. Each phase is accepted only when its evidence gate passes.

## The rule applied in every phase

For every FalkorDB query, command or algorithm: locate its official reference; record the exact image/module/client versions; run a small controlled fixture; compare actual output with independently specified expected results; retain the query, parameters and result. Unsupported or incorrect behavior blocks that feature. A model's confident explanation cannot waive this gate.

The distinction is documented → available locally → parsed/executed → semantically checked → integration checked. Never collapse these into a single “verified” badge.

## Phase 1 — Prove the graph foundation

**Deliver:** graph schema, range indexes, deterministic synthetic fixtures, capability inventory, alternate-chain discovery and compatibility queries, bounded Python AND/OR expansion, documented positive and negative checks. No UI, model calls or provider mutations yet.

Use [the Phase 1 prompt](../prompts/phase-01.md), which specifies the scope and expected evidence. It includes the application algorithm needed to combine graph results; it does not pretend one shortest-path query solves all prerequisites.

**Gate:** FalkorDB returns the right requirements and bindings; discovery produces B's conditional recovery, rejects C's weight limit, preserves a valid R81, rejects stale/wrong-warehouse inputs, and changes output after a catalog change. Phase 1 proves planning facts, not successful shipping or the final execution guarantee.

**Acceptance status (17 October 2026): PASS.** The supplemental runner checks cycle/depth limits, graph isolation, closed-port failure, renamed/permuted fixtures, importer negatives, and a complete 2,020-row producer result. See [machine-readable evidence](../reports/phase-01/acceptance-verification.json).

## Phase 2 — Build the independent provider world

**Deliver:** inventory and carrier simulator with transactional records, stable operation keys, status lookup, seeded fixtures, a controlled clock and precise failure injection.

**Gate:** after-commit response loss leaves a real booking in the simulator ledger. A repeated supported key returns the original result. Agent observations and provider truth remain separate. The evaluator's world audit is unavailable to the agent.

**Implementation status (17 October 2026): core Phase 2 simulator implemented and gate-checked.** See [the Phase 2 evidence report](../reports/phase-02.md) and [machine-readable verification](../reports/phase-02/verification.json). It runs as an independent loopback HTTP process with a SQLite world ledger. Phase 3 remains the next gated phase; this simulator is not yet connected to a Rewire coordinator or FalkorDB observation projector.

## Phase 3 — Enforce execution and reconciliation

**Deliver:** durable intent/attempt/receipt state machine, selected-plan gate, freshness and semantic checks, logical effect claim, coordinator restart behavior, event persistence and explicit unresolved outcomes.

**Gate:** stale plans cannot dispatch; an unresolved shipment blocks cross-provider replacement; crashes at each boundary recover or stay honestly unknown. Query checks and claim writes occur within one coordinator critical section, with provider-side atomic validation at execution. The single-coordinator assumption is enforced.

**Implementation status (17 October 2026): Phase 3 gate passes.** See [Phase 3 evidence](../reports/phase-03.md), [machine-readable verification](../reports/phase-03/verification.json), [coordinator](../src/rewire/execution.py), and [Phase 3 runner](../scripts/verify_phase3.py). The verified path checks all dispatch slots and exact artifact versions, rejects stale revisions, writes an idempotent intent before dispatch, fences an unresolved logical effect, recovers PREPARED and UNKNOWN intents through status lookup, survives coordinator reconstruction after provider and graph commits, validates receipt identity/hash, and idempotently projects the booking into FalkorDB. The separate provider ledger confirms exactly one booking in this controlled scenario.

**Scope boundary:** this proves the protocol against the local simulator's synchronous, idempotent operation contract and one coordinator process. It does not prove distributed multi-coordinator safety or exactly-once behavior for arbitrary real providers. Q11's `NO_EFFECT` path is checked only with a never-submitted key against the simulator's tested 404 behavior; other adapters must independently establish an authoritative absence contract before they may release an effect.

## Phase 4 — Connect the live agent through MCP

**Deliver:** typed graph and action tools, constrained model decisions, bounded calls, query trace, receipt-grounded explanations and recorded model configuration.

**Implementation status:** MCP tool schemas are discovered through the protocol. Graph/run and clock scope are enforced by the host. An operator approves a digest over the precise plan snapshot and revision; model text cannot grant approval. A loopback-only adapter executes dependency steps through durable graph intents, preflight, provider status reconciliation, receipt validation and graph projection. Ordinary sessions do not expose the action tool.

**Gate:** live model execution and changed-fixture graph execution both reach provider-confirmed output. A response lost after provider commit recovers by the stable operation key; the independent provider audit shows one booking. `python scripts/verify_recovery.py` covers the synthetic adapter. The local FalkorDB gate passed; see [the Phase 4 verification report](../reports/phase-04/recovery-verification.json).

**Acceptance status (17 October 2026): PASS.** The live Qwen model selected the MCP action on both base Carrier B and changed Carrier D graphs. The lost booking response reconciled, all four step receipts were recorded, and each isolated provider audit showed exactly one booking. See [recovery verification](../reports/phase-04/recovery-verification.json).

## Phase 5 — Build the complete control room

**Deliver:** graph workspace, goal/status header, candidate comparison, clickable evidence, exact query trace, fault controls, event timeline, provider audit, replay and side-by-side baseline results.

**Gate:** all visual state comes from recorded server activity. UNKNOWN is distinct from failure. Reconnect preserves event order. A reviewer can understand why an action was selected and permitted without opening source files.

**Acceptance status (17 October 2026): PASS.** The local FastAPI application serves a project overview and the live control room. It exposes graph-plan steps, artifacts and events through three exact read-only console queries, uses SSE for ordered durable events, and retains the evaluator-only provider audit outside agent-visible HTTP routes. The deterministic HTTP gate passed the base Carrier B and changed Carrier D paths, a post-commit lost response, repeat approval, expired-reservation blocking and one-booking checks. See [control-room verification](../reports/phase-05/control-room-verification.json).

## Phase 6 — Add counterfactual resilience inspection

**Deliver:** isolated analysis snapshots; “disable this capability” preview; backup plans; BFS impact; WCC catalog islands; optional betweenness prioritization of which failures to analyze.

**Gate:** a snapshot cannot execute provider actions. It shows conditional predicted outcomes and source revision. A centrality score is labeled a heuristic; a criticality claim requires an explicit removal-and-replan result with search completeness disclosed.

## Phase 7 — Add evidence-bearing extensions

**Deliver only when visible:** reviewed OpenAPI contract drafts, UDF compatibility parity, larger-catalog retrieval, bulk ingestion reports, and optional SPpaths/CCH transport estimates.

**Gate:** each feature passes its source/runtime/semantic checks and appears in the UI or README with a concrete use. Unsupported features remain disabled and documented. Do not add PageRank, community detection or another database just to increase algorithm count.

## Phase 8 — Evaluate the complete system

**Deliver:** protocol cases, held-out graph compositions, fair no-graph comparisons, independent world-effect counts and a reproducible result manifest.

**Gate:** report task completion, unresolved outcomes, invalid attempts, duplicate effects, reuse, latency and cost. Explain where graph planning makes no difference. Only measured numbers enter the presentation.

## Phase 9 — Package, demonstrate and publish the explanation

**Deliver:** clean local setup or deployment, public repository, schema/query documentation, licenses, AI-assistance disclosure, three-minute video and blog post.

**Gate:** a fresh reviewer can reproduce the central example. The author can explain every algorithm, validation boundary and limitation. Shipped features are separated from roadmap. The event deadline is checked independently; this roadmap does not change it.

## Solo working method

Keep one phase active. Ask the coding assistant for a change summary, evidence paths, known failures and the next unresolved assumption after each increment. Review schema changes yourself and walk one failure case by hand. The assistant can write code; you remain responsible for understanding and explaining it.
