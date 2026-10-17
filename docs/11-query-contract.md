# 11. Query contract and verification requirements

## Evidence status

**At planning time the query bodies below were proposals, not verified behavior.** Phase 1 has now executed Q00–Q04 and Q01R/Q02R against the local FalkorDB image; see [the Phase 1 evidence report](../reports/phase-01.md) and each run's `queryVerification` matrix for the checked subset. Those checks cover the base fixture, catalog substitution, scope/schema/version/expiry boundaries and Q04 direction. The remaining acceptance gates in the report are still open, so do not treat every query or every possible data shape as fully certified. Later mutation queries have their own phase gates and remain unimplemented.

Use five statuses per query: DOCUMENTED, AVAILABLE, EXECUTED, SEMANTICALLY_CHECKED, INTEGRATION_CHECKED. Store source URL, review date, image digest, module/client versions, query hash, parameters, expected result, actual result and error separately. An entry can be DOCUMENTED and still fail locally.

## Concrete schema contract

One graph contains one run and its versioned catalog. The backend chooses graph names. All IDs are stable application strings. All times below are integer UTC milliseconds; expiresAt = 0 means intentionally non-expiring. Missing required fields are malformed data, not permissive defaults. The controlled simulator clock supplies nowMs. Versions are integers except schemaVersion, which is a string matched exactly.

This table supplements and concretizes document 3. Fields used by the queries are required on their entity unless explicitly optional.

| Label | Required fields |
| --- | --- |
| Run | id, stateRevision, catalogRevision, selectedPlanId (empty when absent), status |
| Goal | id, orderId, warehouseId, destinationZone, weightKg, maxCostUnits, cutoffAt |
| ToolRevision | id, toolId, version, catalogRevision, enabled, adapterId, effectClass, maxWeightKg (0 means unbounded) |
| RequirementSlot | id, name, cardinality (Phase 1 = 1), schemaVersion, minVersion, requiredStatus ('*' accepts any declared usable status), scopeOrder, scopeWarehouse, ruleId |
| ArtifactType | id, schemaVersion |
| Artifact | id, typeId, schemaVersion, version, status, expiresAt, orderId, warehouseId; type-specific payload fields |
| Constraint | id, kind, ruleVersion, parametersJson |
| Plan | id, basedOnRevision, status, searchOutcome, invalidReason (empty initially) |
| PlanStep | id, status, ordinal |
| Decision | id, selectedPlanId, reasonCode, evidenceJson |
| Effect | id, state ('FREE', 'CLAIMED', 'CONFIRMED'), activeIntentId (empty when FREE) |
| Intent | id, logicalEffectId, operationKey, payloadHash, status, providerId, createdAt |
| Attempt | id, startedAt, endedAt (0 until ended), outcome |
| Receipt | id, providerRecordId, payloadDigest, observedAt, status |
| Event | id, sequence, type, timestamp, payloadJson |

Type-specific compatibility includes packageHash, quoteId, priceUnits, serviceId and destinationZone. Each adapter contract declares which artifacts carry these fields and the equality/eligibility rules between them. Unit conversions must be explicit and validated. Required expiry and status checks cannot be inferred from natural-language descriptions.

Relationships from document 3 remain, with these concrete additions:

- Run → HAS_PLAN → Plan; Run → HAS_EFFECT → Effect.
- Effect → HAS_INTENT → Intent; Intent → FOR_STEP → PlanStep.
- Artifact → INSTANCE_OF → ArtifactType must agree with artifact.typeId and schemaVersion.
- BINDS has slotId and expectedVersion; READS_OUTPUT_FROM has slotId and producerPort.
- PlanStep → UNBLOCKS → PlanStep is a derived reverse of DEPENDS_ON for impact analysis only. It is rebuilt from authoritative dependency edges and is never an independent source of execution permission.
- Run → EMITTED → Event uses sequence = the post-transition stateRevision for state-changing events. Diagnostic query traces have a separate trace ID and do not advance that revision.

Phase 1 rejects optional or variable-cardinality slots explicitly. Later support requires a contract change and new cases, not an implicit interpretation.

## Source basis for our query composition

Reviewed references: [MATCH](https://docs.falkordb.com/cypher/match), [OPTIONAL MATCH](https://docs.falkordb.com/cypher/optional-match), [WITH](https://docs.falkordb.com/cypher/with), [SET](https://docs.falkordb.com/cypher/set), [Cypher language](https://docs.falkordb.com/cypher/) and [functions](https://docs.falkordb.com/cypher/functions).

FalkorDB's function reference explicitly distinguishes property existence from unsupported exists(graph-pattern) expressions. These queries use ordinary patterns and explicit rows, avoiding invented APOC/GDS calls or copied Neo4j-only syntax. This source review does not establish correctness of our composed business logic.

Parameters are supplied through the official client, as documented for [GRAPH.QUERY](https://docs.falkordb.com/commands/graph.query). Never interpolate model text into Cypher. Its version option concerns schema caching, not Rewire's application stateRevision.

## Indexes and constraints

Use the documented [range-index syntax](https://docs.falkordb.com/cypher/indexing/range-index), one statement per call:

~~~cypher
CREATE INDEX FOR (r:Run) ON (r.id)
~~~
~~~cypher
CREATE INDEX FOR (t:ToolRevision) ON (t.id)
~~~
~~~cypher
CREATE INDEX FOR (a:Artifact) ON (a.id)
~~~
~~~cypher
CREATE INDEX FOR (a:ArtifactType) ON (a.id)
~~~
~~~cypher
CREATE INDEX FOR (s:RequirementSlot) ON (s.id)
~~~

Apply the same id-index pattern to Goal, Constraint, Plan, PlanStep, Decision, Effect, Intent, Attempt, Receipt and Event. Add an Intent.logicalEffectId index and Event.sequence index when the associated read paths are implemented. Only trusted fixed labels are used by the migration generator.

These are Redis-protocol commands, **not Cypher**:

~~~text
GRAPH.CONSTRAINT CREATE <graph> UNIQUE NODE Artifact PROPERTIES 1 id
GRAPH.CONSTRAINT CREATE <graph> MANDATORY NODE Artifact PROPERTIES 1 id
~~~

Apply ID uniqueness and existence to every entity label after its index exists. The [constraint reference](https://docs.falkordb.com/commands/graph.constraint-create) documents the supporting-index requirement and asynchronous construction. Wait for OPERATIONAL; PENDING is not success. UNIQUE alone does not require non-null values. Application validation still enforces types, relationship cardinality and semantic rules.

### Q00 — Inventory

Execute separately:

~~~cypher
CALL dbms.procedures() YIELD name, mode RETURN name, mode
~~~
~~~cypher
CALL db.indexes()
~~~
~~~cypher
CALL db.constraints()
~~~

Source: [procedure reference](https://docs.falkordb.com/cypher/procedures). Inventory proves registration/status only. Record documented-versus-local differences, including procedure-name casing.

## Alternate chain discovery: Q01–Q03 plus the application planner

There is no claim that the following is a single built-in “repair workflow” algorithm. The bounded AND/OR search is **our Python algorithm**. FalkorDB supplies authoritative producer, requirement, binding and dependency relations at each expansion. The algorithm evaluates shared variables and effects and records its result back into the graph.

### Q01 — Candidate producers and complete requirement slots

~~~cypher
MATCH (t:ToolRevision)-[:PRODUCES]->(out:ArtifactType {id: $typeId})
WHERE t.enabled = true
  AND t.catalogRevision = $catalogRevision
  AND (t.maxWeightKg = 0 OR t.maxWeightKg >= $weightKg)
OPTIONAL MATCH (t)-[:REQUIRES]->(slot:RequirementSlot)-[:OF_TYPE]->(input:ArtifactType)
OPTIONAL MATCH (t)-[:CONSUMES]->(consumedType:ArtifactType)
RETURN t.id AS toolId, t.toolId AS publicToolId, t.version AS toolVersion,
       t.enabled AS enabled, t.maxWeightKg AS maxWeightKg,
       t.adapterId AS adapterId, t.effectClass AS effectClass,
       t.outputBindingsJson AS outputBindingsJson,
       slot.id AS slotId, slot.name AS slotName, input.id AS inputTypeId,
       consumedType.id AS consumedTypeId,
       slot.cardinality AS cardinality, slot.schemaVersion AS schemaVersion,
       slot.minVersion AS minVersion, slot.requiredStatus AS requiredStatus,
       slot.scopeOrder AS scopeOrder, slot.scopeWarehouse AS scopeWarehouse,
       slot.ruleId AS ruleId, slot.outputBindingsJson AS slotOutputBindingsJson
ORDER BY toolId, slotId
~~~

Parameters: typeId, catalogRevision, weightKg from the validated goal. Return all required slots; no LIMIT that can hide one. Enforce configured catalog/result limits and fail explicitly on truncation. A zero-input producer has one row with null slotId; import validation distinguishes this from malformed missing edges.

To explain a weight rejection, query the same producer relation without the enabled/weight filters and return its declared properties. Do not explain an absent row by guessing which condition failed.

### Q01R — Producer facts for rejection explanations

~~~cypher
MATCH (t:ToolRevision)-[:PRODUCES]->(:ArtifactType {id: $typeId})
WHERE t.catalogRevision = $catalogRevision
RETURN t.id AS toolId, t.version AS toolVersion,
       t.enabled AS enabled, t.maxWeightKg AS maxWeightKg
ORDER BY toolId
~~~

The application compares these observed properties with the goal and records reason codes. It does not infer provider reliability from absence in Q01.

### Q02R — Observed artifact candidates for transparent rejection reasons

~~~cypher
MATCH (run:Run {id: $runId})-[:HAS_ARTIFACT]->(a:Artifact)
MATCH (a)-[:INSTANCE_OF]->(ty:ArtifactType {id: $typeId})
RETURN a.id AS artifactId, a.typeId AS typeId, a.schemaVersion AS schemaVersion,
       a.version AS version, a.status AS status, a.expiresAt AS expiresAt,
       a.orderId AS orderId, a.warehouseId AS warehouseId
ORDER BY artifactId
~~~

Q02R is diagnostic only. Python compares these rows with slot requirements to explain why candidates were rejected. Q02 remains the database-filtered compatible binding list. The planner fails closed if their accepted IDs disagree with application validation.

### Q02 — Compatible observed artifacts, preserving missing inputs

~~~cypher
MATCH (run:Run {id: $runId})
MATCH (t:ToolRevision {id: $toolId})-[:REQUIRES]->(slot:RequirementSlot)-[:OF_TYPE]->(ty:ArtifactType)
WHERE t.enabled = true AND t.catalogRevision = run.catalogRevision
OPTIONAL MATCH (run)-[:HAS_ARTIFACT]->(a:Artifact)-[:INSTANCE_OF]->(ty)
WHERE a.schemaVersion = slot.schemaVersion
  AND a.version >= slot.minVersion
  AND (slot.requiredStatus = '*' OR a.status = slot.requiredStatus)
  AND (a.expiresAt = 0 OR a.expiresAt > $nowMs)
  AND (slot.scopeOrder = false OR a.orderId = $orderId)
  AND (slot.scopeWarehouse = false OR a.warehouseId = $warehouseId)
RETURN slot.id AS slotId, slot.name AS slotName, ty.id AS typeId,
       a.id AS artifactId, a.version AS artifactVersion
ORDER BY slotId, artifactId
~~~

A null artifactId means the slot has no current compatible artifact. The planner may search for a producer; it must not drop the slot. This query filters basic compatibility. Cross-artifact quote/package equality, mutually exclusive resources and provider-specific conditions are deterministic application predicates, explicitly logged alongside query evidence.

### Q03 — Exact observed artifact for a planned binding

~~~cypher
MATCH (run:Run {id: $runId})-[:HAS_ARTIFACT]->(a:Artifact {id: $artifactId})
MATCH (a)-[:INSTANCE_OF]->(ty:ArtifactType {id: $typeId})
WHERE run.stateRevision = $expectedRevision
  AND a.version = $expectedArtifactVersion
  AND a.schemaVersion = $schemaVersion
  AND a.status = $requiredStatus
  AND (a.expiresAt = 0 OR a.expiresAt > $nowMs)
  AND a.orderId = $orderId
  AND a.warehouseId = $warehouseId
RETURN a.id AS artifactId, a.typeId AS typeId, a.schemaVersion AS schemaVersion,
       a.version AS version, a.status AS status, a.expiresAt AS expiresAt,
       a.orderId AS orderId, a.warehouseId AS warehouseId
~~~

This query is for an order-and-warehouse-scoped binding, such as a reservation. Do not use it unchanged for a global capability artifact. Zero rows is a rejection requiring a reason lookup, not permission to recreate or mutate anything.

### What a complete alternate plan means

Starting from Booking, Q01 finds enabled eligible producers. Q02 tries every required slot against observed artifacts. Missing slots recursively invoke Q01. Future inputs are producer-step/output-port references; they are not invented observations. Python joins compatible bindings, checks cycles/consumption, and returns STRUCTURALLY_VALID with all unresolved runtime conditions. It labels SEARCH_LIMIT_REACHED separately from exhaustive impossibility.

In the core fixture, B dispatch depends on R81 plus pickup, quote and label. A is unavailable and C cannot handle 8 kg. R81 is reused only if Q03 passes. A future quote has unknown price until read; this remains a condition, never an assumed 760-unit observation.

## Invalidation on failure

### Q04 — Identify downstream steps

~~~cypher
MATCH (p:Plan {id: $planId})-[:HAS_STEP]->(changed:PlanStep {id: $stepId})
MATCH (p)-[:HAS_STEP]->(dependent:PlanStep)
MATCH (dependent)-[:DEPENDS_ON*1..12]->(changed)
RETURN DISTINCT dependent.id AS stepId, dependent.status AS status
~~~

The trigger step is handled separately. Phase 1's maximum dependency depth is 12 and import/search reject longer plans; later bounds require completeness checks. Confirmed historical steps remain confirmed. Invalidating a plan does not reverse a world effect or resolve an UNKNOWN intent.

### Q05 — Invalidate a plan using a now-unavailable tool

~~~cypher
MATCH (run:Run {id: $runId})-[:HAS_PLAN]->(p:Plan {id: $planId})
MATCH (p)-[:HAS_STEP]->(:PlanStep)-[:USES_TOOL]->(t:ToolRevision {id: $toolId})
WHERE run.stateRevision = $expectedRevision AND t.enabled = false
WITH DISTINCT run, p
SET p.status = 'INVALIDATED', p.invalidReason = 'TOOL_UNAVAILABLE',
    run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'plan.invalidated',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN p.id AS planId, run.stateRevision AS revision, e.id AS eventId
~~~

Only the coordinator may perform this transition. The tool availability update is an earlier controlled transition; pass the resulting revision here. Persist observed failure separately with its effect-certainty classification. No-match, duplicate event and retry cases must be handled explicitly by request identity and re-reading state.

## Preflight and mutation authorization

### Q06 — Retrieve every slot and its current binding for inspection

~~~cypher
MATCH (run:Run {id: $runId})-[:HAS_PLAN]->(p:Plan {id: $planId})
MATCH (p)-[:HAS_STEP]->(step:PlanStep {id: $stepId})-[:USES_TOOL]->(t:ToolRevision)
WHERE run.stateRevision = $expectedRevision
  AND run.selectedPlanId = p.id AND p.status = 'SELECTED'
  AND step.status = 'READY' AND t.enabled = true
  AND t.catalogRevision = run.catalogRevision
OPTIONAL MATCH (t)-[:REQUIRES]->(slot:RequirementSlot)-[:OF_TYPE]->(ty:ArtifactType)
OPTIONAL MATCH (step)-[binding:BINDS]->(a:Artifact)
WHERE binding.slotId = slot.id
RETURN run.stateRevision AS revision, t.id AS toolId,
       slot, ty.id AS requiredTypeId, binding.expectedVersion AS expectedVersion, a
ORDER BY slot.id, a.id
~~~

This intentionally returns invalid or missing bindings rather than hiding them in WHERE. The executor requires exactly one binding for every required slot; verifies run membership, artifact type/schema, exact expected version, freshness/status, shared-variable predicates and payload identity; and denies unexpected bindings. A zero-input tool requires an imported zero-slot contract. No returned rows is denial. The query's rows are evidence, not an authorization token.

### Q07 — Inspect the logical effect fence

~~~cypher
MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect {id: $effectId})
OPTIONAL MATCH (effect)-[:HAS_INTENT]->(i:Intent)
RETURN effect.state AS effectState, effect.activeIntentId AS activeIntentId,
       i.id AS intentId, i.status AS intentStatus, i.operationKey AS operationKey
~~~

The Effect record is created with the run, under an ID constraint. Missing effect is denial, not FREE. A CLAIMED or CONFIRMED effect blocks a new intent. Retrying or reconciling an existing intent is a separate protocol preserving its original operation identity.

### Q08 — Claim an effect and persist PREPARED intent

~~~cypher
MATCH (run:Run {id: $runId})-[:HAS_PLAN]->(p:Plan {id: $planId})
MATCH (run)-[:HAS_EFFECT]->(effect:Effect {id: $effectId})
MATCH (p)-[:HAS_STEP]->(step:PlanStep {id: $stepId})-[:USES_TOOL]->(t:ToolRevision)
WHERE run.stateRevision = $expectedRevision
  AND run.selectedPlanId = p.id AND p.status = 'SELECTED'
  AND step.status = 'READY' AND t.enabled = true
  AND t.catalogRevision = run.catalogRevision AND effect.state = 'FREE'
CREATE (i:Intent {
  id: $intentId, logicalEffectId: $effectId, operationKey: $operationKey,
  payloadHash: $payloadHash, status: 'PREPARED', providerId: $providerId,
  createdAt: $nowMs
})
CREATE (effect)-[:HAS_INTENT]->(i)
CREATE (i)-[:FOR_STEP]->(step)
CREATE (step)-[:AUTHORIZED_BY]->(i)
SET effect.state = 'CLAIMED', effect.activeIntentId = i.id,
    step.status = 'PREPARED', run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'intent.prepared',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN i.id AS intentId, run.stateRevision AS revision
~~~

Q06/Q07, complete semantic validation and Q08 execute under the single coordinator's critical section. All application writers share that authority. Q08 is not a standalone all-input validator or a substitute for tested concurrency behavior. The provider additionally enforces current resource conditions atomically. No external call occurs until the intent meets the configured durability requirement. Fail closed if graph/query results are uncertain.

The implemented coordinator wraps the revision-guarded claim in a process-local lock. Before creating an intent, `claim_intent` reads by `(runId, effectId, operationKey)` using Q08C. An exact payload/provider/step match returns the existing intent for a retried client request; a changed payload or identity is an error. A first claim runs Q08 while still holding that lock. All application-side graph writers for this coordinator must follow the same lock and revision discipline. This is a single-process assumption, not distributed locking.

## Reconciliation after a lost response

### Q09 — Gather original operation and evidence

~~~cypher
MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect)-[:HAS_INTENT]->(i:Intent {id: $intentId})
OPTIONAL MATCH (i)-[:HAS_ATTEMPT]->(a:Attempt)
OPTIONAL MATCH (receipt:Receipt)-[:CONFIRMS]->(i)
RETURN effect.id AS effectId, effect.state AS effectState,
       i.operationKey AS operationKey, i.payloadHash AS payloadHash,
       i.providerId AS providerId, i.status AS intentStatus, a, receipt
~~~

Cypher cannot establish an external booking's existence from a missing graph receipt. The adapter calls provider status with the original key, validates the returned payload and identity, then submits a controlled transition. A not-found response must be authoritative under the provider's consistency contract before it can mean NO_EFFECT.

### Q10 — Record an authoritative confirmed receipt

~~~cypher
MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect)-[:HAS_INTENT]->(i:Intent {id: $intentId})
MATCH (i)-[:FOR_STEP]->(step:PlanStep)
MATCH (i)-[:HAS_ATTEMPT]->(a:Attempt {id: $statusAttemptId})
WHERE run.stateRevision = $expectedRevision
  AND effect.state = 'CLAIMED' AND effect.activeIntentId = i.id
  AND i.status IN ['PREPARED', 'IN_FLIGHT', 'UNKNOWN', 'INVALID_OUTPUT']
  AND i.payloadHash = $validatedPayloadHash
CREATE (receipt:Receipt {
  id: $receiptId, providerRecordId: $providerRecordId,
  payloadDigest: $payloadDigest, observedAt: $nowMs, status: 'CONFIRMED'
})
CREATE (a)-[:OBSERVED]->(receipt)
CREATE (receipt)-[:CONFIRMS]->(i)
SET i.status = 'CONFIRMED', effect.state = 'CONFIRMED',
    a.outcome = 'CONFIRMED', a.endedAt = $nowMs,
    step.status = 'CONFIRMED', run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'effect.confirmed',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN receipt.id AS receiptId, i.id AS intentId, run.stateRevision AS revision
~~~

The status lookup attempt is recorded before this query. All validated parameters come from the executor, not the LLM. This transition records effect confirmation; it does not mark the entire run successful. Artifact materialization and final goal checks follow from the accepted receipt through an idempotent projector. A crash between confirmation and projection resumes that projector without calling dispatch again.

Q13 is a read projection for the run's intent/attempt/receipt/artifact/event timeline. Q14 reads one Booking projection by artifact and provider record IDs. The coordinator checks Q14 under the same local lock before retrying Q12; an identical confirmed projection is returned as a replay, while conflicting stored identity fails closed. This makes a lost UI response after graph commit recoverable without repeating provider dispatch.

The verified Phase 3 path covers PREPARED, IN_FLIGHT, UNKNOWN, status reconciliation, CONFIRMED, authoritative NO_EFFECT for a never-submitted simulator key, and idempotent artifact projection. Q09A accepts PREPARED, IN_FLIGHT or UNKNOWN intents to begin status reconciliation after restart; it does not itself authorize dispatch. The gate verifies that a non-authoritative absence flag is denied and an authoritative one releases the effect. Each real adapter still needs its own documented visibility and absence semantics. Never infer that a missing graph receipt proves no external action occurred.

## Algorithm tools: exact proposed calls and honest meanings

### A01 — BFS impact candidates

~~~cypher
MATCH (s:PlanStep {id: $stepId})
CALL algo.BFS(s, 12, 'UNBLOCKS') YIELD nodes, edges
RETURN nodes, edges
~~~

[BFS reference](https://docs.falkordb.com/algorithms/bfs). The procedure overview uses algo.BFS while the detailed page uses algo.bfs. Record the registered name and verify case behavior rather than assuming interchangeability. Validate traversal direction, inclusion of the source and depth boundaries on a small asymmetric chain. Use Q04 as the direction-explicit authority until parity is established. Do not treat array position as graph depth.

### A02 — WCC catalog islands

~~~cypher
CALL algo.WCC({
  nodeLabels: ['ToolRevision', 'RequirementSlot', 'ArtifactType'],
  relationshipTypes: ['REQUIRES', 'OF_TYPE', 'PRODUCES']
}) YIELD node, componentId
RETURN node.id AS nodeId, componentId
~~~

[WCC reference](https://docs.falkordb.com/algorithms/wcc). Run in an analysis graph containing only the intended catalog revision. WCC ignores direction: different components reveal disconnected regions; being in one component does not prove a directed, compatible plan. Test an island and a directionally impossible chain. Component numbers are run-local labels, not durable IDs.

### A03 — Betweenness for ordering failure experiments

~~~cypher
CALL algo.betweenness({
  nodeLabels: ['Capability'], relationshipTypes: ['FEEDS'],
  samplingSize: 32, samplingSeed: 17
}) YIELD node, score
RETURN node.id AS capabilityId, score
ORDER BY score DESC, capabilityId
~~~

[Betweenness reference](https://docs.falkordb.com/algorithms/betweenness-centrality). Capability/FEEDS is a separate, versioned analysis projection: an edge means one registered tool can supply a required input type of another. It discards AND and value constraints, so scores only prioritize removal experiments. The fixed nonzero seed stabilizes sampling; test full-source versus sampled behavior on the chosen fixture. High score is not a proof of a single point of failure.

### A04 — Optional weighted route estimate

~~~cypher
MATCH (source:Hub {id: $sourceId}), (target:Hub {id: $targetId})
CALL algo.SPpaths({
  sourceNode: source, targetNode: target, relTypes: ['ROUTE'],
  weightProp: 'costUnits', relDirection: 'outgoing',
  maxLen: 12, pathCount: 1
}) YIELD path, pathWeight
RETURN path, pathWeight
~~~

[SPpaths reference](https://docs.falkordb.com/algorithms/sppath). Every ROUTE edge has an explicit nonnegative integer costUnits. Use a separately filtered graph for eligible transport routes. Test a known weighted diamond, unreachable target and direction reversal. A route result is not a tool workflow or authoritative carrier quote. Do not assume pathCount produces a general k-shortest-path enumerator.

### A05 — PageRank diagnostic, excluded from the default product

~~~cypher
CALL algo.pageRank('Capability', 'FEEDS') YIELD node, score
RETURN node.id AS capabilityId, score
ORDER BY score DESC, capabilityId
~~~

The signature is documented in the [procedure reference](https://docs.falkordb.com/cypher/procedures). It ranks structural prominence in this projection. No reviewed evidence makes that equivalent to business criticality, action correctness or a failure probability. Do not register it as a production decision tool without a useful evaluated objective.

### Actual criticality experiment

Copy the analysis state, disable one candidate tool, rerun the same bounded planner and compare unmet goals and viable alternatives. Report “no alternative found within budget” when search was truncated. Even an exhaustive result is conditional on this catalog and world model. This is our application analysis, not a fabricated FalkorDB criticality procedure.

## Extension gates

| Feature | Verified documentation | Remaining requirement |
| --- | --- | --- |
| CCH | [CCH index](https://docs.falkordb.com/cypher/indexing/cch-index) | Weighted routing only; exact implementation query deferred until workload and image are selected |
| UDF | [UDF reference](https://docs.falkordb.com/udfs/) | Read-only custom logic; validate API and return types; no mutation or network assumptions |
| Graph snapshots | [GRAPH.COPY](https://docs.falkordb.com/commands/graph.copy) | Source/destination isolation; never provider rollback |
| Bulk loading | [Official loader](https://github.com/FalkorDB/falkordb-bulk-loader) | Ingestion compatibility and measured workload; no algorithm claim |
| Full-text/vector search | [Full-text](https://docs.falkordb.com/cypher/indexing/fulltext-index), [vector](https://docs.falkordb.com/cypher/indexing/vector-index) | Candidate recall and exact validation after retrieval |
| Query diagnostics | [EXPLAIN](https://docs.falkordb.com/commands/graph.explain), [PROFILE](https://docs.falkordb.com/commands/graph.profile) | Use disposable fixtures; PROFILE executes the query, including mutations |

No executable body for a deferred feature is invented here. Add its source-linked query and semantic fixture before enabling it. READMEs and demos must distinguish “documented by FalkorDB” from “used and checked by Rewire.”
