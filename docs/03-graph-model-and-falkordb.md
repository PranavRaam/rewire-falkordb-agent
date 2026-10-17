# 3. Graph model and FalkorDB capabilities

**Revision 2:** this document explains the conceptual model. [Document 11](11-query-contract.md) defines the concrete property contract, exact proposed query bodies, corrected algorithm uses and runtime checks. Its Q IDs replace the earlier conceptual inventory below. All queries remain unexecuted until the Phase 1 evidence gate.

## The graph's central responsibility

FalkorDB stores the relationships from which Rewire derives available actions. The planner cannot use a parallel hardcoded catalog when graph queries fail. Its in-memory search state is transient and tied to the graph revision that produced it.

The representation has two layers: capability knowledge describes what registered tools can do; execution knowledge describes what this run has observed and attempted. An artifact type is not an actual usable artifact.

## Nodes

All entities have an application-generated stable ID. Never expose database-internal node IDs as durable public identifiers.

| Label | Important properties | Meaning |
| --- | --- | --- |
| Run | id, stateRevision, status, scenarioId | One isolated execution |
| Goal | id, kind, orderId, constraintsVersion | Typed desired outcome |
| ToolRevision | id, toolId, version, adapterId, enabled, effectClass | Immutable registered capability revision |
| RequirementSlot | id, name, cardinality, bindingRuleId | A named input requirement |
| ArtifactType | id, schemaVersion | Abstract type such as Reservation |
| Artifact | id, typeId, orderId, warehouseId, version, status, expiresAt | Observed concrete output or input |
| Constraint | id, ruleVersion, kind | Declarative condition with a deterministic evaluator |
| Plan | id, basedOnRevision, status, searchOutcome | Candidate or selected plan |
| PlanStep | id, ordinal, status | One planned tool invocation |
| Decision | id, selectedPlanId, reasonCode | Selection with structured justification |
| Intent | id, logicalEffectId, operationKey, payloadHash, status | Durable authorization and operation identity |
| Attempt | id, startedAt, endedAt, outcome | A transport attempt for an intent |
| Receipt | id, providerRecordId, observedAt, payloadDigest | Validated provider evidence |
| Event | id, sequence, type, timestamp, payloadJson | Durable UI/audit update |

Structured payloads that exceed convenient scalar graph properties may be stored as canonical JSON strings. Fields used for matching, filtering or indexing must remain explicit properties or relationships. Schemas and validators are versioned source files, not executable code supplied by users.

## Relationships and direction

| Relationship | Purpose |
| --- | --- |
| Run → HAS_GOAL → Goal | Identify the desired outcome |
| Goal → NEEDS_TYPE → ArtifactType | Start backward expansion |
| ToolRevision → PRODUCES → ArtifactType | Find alternative producers |
| ToolRevision → REQUIRES → RequirementSlot → OF_TYPE → ArtifactType | Preserve AND semantics and input names |
| RequirementSlot → CHECKED_BY → Constraint | Bind compatibility conditions |
| ToolRevision → CONSUMES → ArtifactType | Resource effects for forward validation |
| Run → HAS_ARTIFACT → Artifact → INSTANCE_OF → ArtifactType | Concrete observed state |
| Plan → HAS_STEP → PlanStep → USES_TOOL → ToolRevision | Inspectable proposed actions |
| PlanStep → DEPENDS_ON → PlanStep | Dependent points toward prerequisite |
| PlanStep → BINDS → Artifact | Concrete inputs; relationship has slotId |
| PlanStep → READS_OUTPUT_FROM → PlanStep | Future input binding; relationship has slotId and producerPort |
| PlanStep → EXPECTS → ArtifactType | Outputs not produced yet |
| PlanStep → AUTHORIZED_BY → Intent → HAS_ATTEMPT → Attempt | Action provenance |
| Attempt → OBSERVED → Receipt | Transport result evidence |
| Artifact → PRODUCED_BY → Attempt | Actual artifact provenance |
| Receipt → CONFIRMS → Intent | Reconciliation evidence can confirm an older intent |
| Decision → SUPPORTS → Plan | Selected alternative with evidence references |
| Run → EMITTED → Event | Durable event stream |

Goal-specific predicates include exactly one confirmed booking, matching order/quantity/origin/destination, valid price/cutoff, and a settled inventory record. A Booking type alone does not establish these facts.

## Contract semantics

For dispatch B, every requirement must hold:

- Reservation is HELD, unexpired and belongs to this order and warehouse.
- Pickup identifier resolves the same warehouse.
- Quote applies to the same package, origin, destination and service, and is still valid.
- Label matches that quote and package.
- No unresolved or confirmed conflicting shipment effect exists for this logical goal.

Dispatch consumes the held reservation and produces a booking. Consumed artifacts remain in the history but cease to satisfy a requirement for a HELD reservation.

Declared compatibility is implemented as explicit versioned predicates. An LLM explanation never substitutes for their evaluation.

## Authoritative query inventory

The conceptual examples from revision 1 have been replaced by [document 11](11-query-contract.md). It contains concrete Q00–Q10 query bodies, Q01R rejection evidence, A01–A05 algorithm calls, parameter contracts, source references and verification requirements. This avoids two competing query inventories.

All proposed bodies are documentation-reviewed and runtime-unverified. Phase 1 verifies discovery and binding queries; the later execution phase verifies mutation transitions. The graph remains server-selected and no model-supplied graph name or arbitrary Cypher is accepted.

## Capability portfolio

| Capability | Product job | Adoption gate |
| --- | --- | --- |
| Cypher pattern matching and bounded traversal | Discover producers, requirements, affected work and evidence chains | Core; results must alter actual decisions |
| Indexes and constraints | Stable entity lookup and schema integrity | Verify supported syntax and inspect plans |
| Built-in BFS or equivalent bounded traversal | Explore affected dependency regions | Compare with reference traversal; respect direction and bounds |
| Read-only UDF | Optional compatibility implementation with visible reason codes | Stretch; reference evaluator first, runtime and parity evidence required |
| Full-text and vector indexes | Find candidate tools in a larger catalog | Measure candidate recall; exact constraints remain authoritative |
| GRAPH.COPY | Preserve a graph snapshot for plan comparison | Branch is isolated and cannot execute external actions |
| GRAPH.BULK via bulk loader | Import larger synthetic catalogs efficiently | Compare loading methods at declared sizes |
| CCH | Repeated route-cost estimates in an optional transport graph | Stretch; not workflow recovery; omit if no visible workload |
| EXPLAIN / PROFILE | Diagnose query costs | Save representative plans and timings |
| Multiple named graphs | Isolate runs, evaluation cases and snapshots | Server authorization still required |

The [procedure reference](https://docs.falkordb.com/cypher/procedures) documents graph introspection, search and algorithms. Availability and behavior must be checked on the installed version; a documentation listing is not a local execution result.

## A custom UDF with a defensible purpose

Proposed library: RewireContracts, with a function such as compatibleBinding. It evaluates explicit properties for a tool slot and candidate artifact, given a fixed evaluation time and contract version. It returns structured compatibility information supported by the chosen runtime, or a stable reason code with details assembled by the query.

It performs no network calls, generates no secrets and changes no world or graph state. Limit graph traversal and input size. Compare its result with a small Python reference over normal and adversarial cases before treating it as authoritative.

FalkorDB documents JavaScript UDFs, registration through falkor.register, and management with GRAPH.UDF. The current API uses graph.traverse; older examples using falkor.traverse need migration. UDF graph access is read-only. [Official UDF documentation](https://docs.falkordb.com/udfs/)

Use the existing supported implementation when it already does the job. RedisGraph ancestry is a research lead, not evidence that a missing feature must be ported. Any code reuse needs API compatibility and license review; do not introduce a second legacy database into the core.

## CCH: a concrete extension, with the right boundary

If the product models transport hubs, create a directed weighted network of warehouse → regional hub → destination zone. The planner may ask for a low-cost feasible route estimate repeatedly while comparing carriers. Give every edge an explicit weight and enforce package/service eligibility before building the relevant routing view.

FalkorDB's CCH index supports weighted point-to-point path queries. Topology changes can cause expensive rebuilding, so measure updates as well as reads. It cannot by itself enforce all workflow prerequisites, multiple resource constraints or uncertain effects. [CCH documentation](https://docs.falkordb.com/cypher/indexing/cch-index)

Keep authoritative carrier quotes separate from estimates. If exact time-dependent restrictions cannot be represented correctly, label the route as an estimate or omit this feature. Do not add a large routing subsystem solely to display CCH in a feature list.

## Bulk import and scale

Use a small authored catalog for comprehension. Generate controlled larger catalogs with known dependency depth, branching factor, incompatible alternatives and connected components for scalability experiments. Record seed, generator version, node/edge counts, query load and relevance distribution.

The [FalkorDB bulk loader](https://github.com/FalkorDB/falkordb-bulk-loader) imports CSV data through GRAPH.BULK. This is an ingestion mechanism, not an algorithm or UDF. Benchmark importer throughput separately from planning and agent latency.

## Graph snapshots and counterfactuals

[GRAPH.COPY](https://docs.falkordb.com/commands/graph.copy) can clone a graph for inspection. Copy the graph's model state, annotate its source revision, then run a pure transition simulator on the branch. Do not attach action credentials to a branch.

A snapshot does not clone the external provider world or prove that a predicted outcome will occur. Show estimated cost and predicted steps as estimates. Replay uses recorded events; live execution always revalidates the current source graph and provider conditions.

## Why the database is essential

Remove the graph and Rewire loses its tool requirements, binding relationships, dependency impact, operation history and evidence paths. It must stop planning and mutating rather than reconstruct a hidden fallback from code. Other databases could implement related systems; the claim is that this implementation genuinely depends on FalkorDB, not that the problem is mathematically impossible elsewhere.
