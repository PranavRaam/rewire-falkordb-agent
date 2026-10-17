# 4. Planner and execution protocol

## Separate three decisions

1. **Discovery:** which tools could contribute to the goal?
2. **Planning:** which sequence or partial order satisfies every condition?
3. **Execution:** is this particular action still permitted now?

An agent can help select relevant goals, tools and alternatives. A deterministic validator decides whether the resulting plan is executable. The provider ultimately decides whether an external mutation succeeds under its own atomic checks.

## Planning representation

Represent an observed state as available artifact IDs and versions, consumed resources, unresolved logical effects, relevant tool revisions and a fixed planning-time snapshot. Preserve immutable facts separately from observations that may expire.

A tool has named input slots, outputs, preconditions, effects, binding rules and an adapter. Multiple input slots are conjunctive: all are required. Multiple producers are alternatives. This forms an AND/OR planning problem with concrete values and effects, not merely a shortest path over tool names.

### Planning sequence

1. Read the graph revision and unmet goals.
2. Ask the graph for producers of each unmet artifact type.
3. Expand all requirement slots of each candidate producer.
4. Bind existing artifacts when they satisfy type, identity, status and lifetime constraints.
5. Recursively find producers for missing inputs, recording shared variables such as order ID and warehouse ID.
6. Forward-simulate candidate steps. Apply consumed-resource effects so the same reservation cannot be allocated twice.
7. Reject candidates with conflicting bindings, unresolved effects, impossible prerequisites or declared policy violations.
8. Rank feasible candidates and return a bounded set with evidence.
9. Mark the result with the graph revision, explored-state count, depth limit and completeness status.

Use bounded best-first search initially. A beam is an optional speed/recall tradeoff, exposed in the configuration and evaluation. Canonicalize states and reject cycles that produce no new useful state. Search can return FOUND, EXHAUSTIVE_NO_PLAN, or SEARCH_LIMIT_REACHED. Only a fully explored finite search permits EXHAUSTIVE_NO_PLAN.

### Future outputs and conditional plans

A quote that has not been requested has no observed price. A proposed label has no actual artifact ID. Represent future inputs as explicit producer-step/output-port references, then resolve them to real artifacts after successful execution. Preserve shared-variable constraints across those references.

Distinguish STRUCTURALLY_VALID from READY_TO_EXECUTE. A structurally valid B plan says that registered tools can produce its required inputs, subject to runtime checks. Only its currently ready steps may execute. A later quote above the budget invalidates the downstream dispatch and triggers replanning; the planner must not invent a qualifying price to declare the whole plan feasible.

Pure simulation propagates declared possible outputs and effects, with unknown values marked unknown. It predicts neither an external provider's eventual response nor guaranteed completion. The UI labels such branches conditional until the necessary observations arrive.

### Ranking that remains explainable

Apply hard constraints before preferences. Among valid plans, use a documented ordering:

1. Avoid unresolved conflicting effects; these are forbidden, not penalized.
2. Meet the user's price/cutoff/resource requirements.
3. Minimize new mutating operations where reuse is valid.
4. Prefer lower incremental cost, then estimated duration.
5. Use stable IDs to break exact ties reproducibly.

Allow explicit user preferences to change ordering, and record the change. Do not call a weighted score a calibrated probability of success. When cost or duration is unknown, expose uncertainty and apply the stated policy. A quote is observed data; a predicted tool duration is an estimate.

## Action eligibility

Before each external mutation, verify:

- The selected plan is current and the step belongs to it.
- The exact tool revision is enabled and authorized.
- All required artifacts are bound; their IDs and versions match.
- Their statuses, expiry and cross-artifact equality constraints hold.
- The relevant logical effect has no conflicting IN_FLIGHT, UNKNOWN or confirmed intent.
- The submitted payload matches the validated binding set.

The graph's application stateRevision is our concurrency field. It is not the schema-cache version option of GRAPH.QUERY. Query configuration is documented separately in [FalkorDB's GRAPH.QUERY reference](https://docs.falkordb.com/commands/graph.query).

## State machines

### Workflow status

READY → RUNNING → RECOVERING → SUCCEEDED

Additional explicit states: BLOCKED, PAUSED_UNKNOWN, FAILED and CANCEL_REQUESTED. Cancellation initially means stop scheduling new work and reconcile in-flight effects. It must not imply that a provider booking has been undone.

### Intent status

| State | Meaning | Permitted next behavior |
| --- | --- | --- |
| PREPARED | Persisted before transport | Begin call or reconcile after restart |
| IN_FLIGHT | Call may have reached provider | Await result; after interruption reconcile |
| CONFIRMED | Valid receipt establishes the intended effect | Do not repeat effect |
| NO_EFFECT | Authoritative evidence says operation did not execute | Replan or retry according to policy |
| UNKNOWN | Insufficient evidence about execution | Status reconciliation; block conflicting mutation |
| INVALID_OUTPUT | Response does not satisfy its contract | Assess effect certainty; reconcile if mutation may have occurred |

INVALID_OUTPUT is not automatically NO_EFFECT. Keep response validity and effect certainty as separate stored fields where necessary. For example, a malformed booking response may conceal a real booking.

## Durable action protocol

1. Under a short coordinator lock, read current state and validate the request.
2. Allocate a logical effect ID scoped to the goal, such as shipment:O-104.
3. Create or reuse an intent with a stable provider operation key and canonical payload hash.
4. Persist PREPARED and an event. Apply the configured persistence guarantees before proceeding.
5. Persist IN_FLIGHT, release the local lock and call the provider.
6. Validate the returned schema and semantic constraints.
7. Under the lock, commit the resulting graph transition, receipt, artifacts and event with an expected application revision.
8. On ambiguous transport failure, persist UNKNOWN when possible; otherwise restart recovery handles the unfinished intent.
9. Reconcile using authoritative status, the original operation key and matching payload identity.
10. Verify final provider outcome before marking the goal satisfied.

Never hold a database or process lock during an LLM or network call. Another request sees the durable in-flight intent and is denied a conflicting effect. Initially run exactly one coordinator process for this authority boundary. Multiple workers require a tested distributed fencing/claim protocol; do not enable them by changing a server flag.

The external provider must atomically check its own current resource versions and preconditions. A correct graph read cannot prevent an external resource from changing before the network call.

## Crash windows

| Crash point | Recovery behavior |
| --- | --- |
| Before intent is persisted | No external call was authorized |
| After PREPARED, before call | Treat as potentially attempted after restart; query status first |
| After provider commit, before response | Status lookup resolves original operation |
| After receipt arrives, before graph commit | Status lookup restores the same evidence |
| After graph commit, before HTTP response to UI | Repeated client request returns existing intent/result |

A status response of “not found” permits a new attempt only if the provider contract makes it authoritative after any visibility delay and excludes a still-running original operation. Otherwise it remains UNKNOWN. Reuse the same operation key for retries within the provider's supported idempotency scope; never invent a new key merely to bypass a duplicate response.

Prevent cross-provider duplication by fencing the logical effect, not just by deduplicating one provider's requests. While B might already have shipped, C must not be allowed to ship the same goal.

## Boundaries of the guarantee

FalkorDB and an external provider do not share one atomic transaction. The protocol combines durable intent, provider idempotency, authoritative reconciliation and guarded scheduling. Exactly-once outcomes cannot be guaranteed for arbitrary APIs that lack these properties, or beyond their retention guarantees.

The simulator can supply strong atomic contracts so we can test the protocol. The UI must state those assumptions when demonstrating absence of duplicates. Future real integrations require adapter-specific analysis.

## Explanations are structured evidence

For each decision, store selected plan ID, goal predicates, candidate IDs, binding IDs, rejected constraint codes, query IDs, graph revision and relevant receipts. The explanation renderer turns those records into readable statements.

Example: “R81 is still usable: inventory status at 15:21 reports HELD until 15:40. Carrier C is ineligible: its 5 kg maximum is below the order's 8 kg weight. Carrier B requires pickup, quote and label, which this plan can produce.”

This is an audit of explicit inputs and actions. It is not a claim to expose the model's private internal reasoning.
