# 9. Research and technical decisions

Research date: 17 October 2026. Documentation describes product capabilities; the selected Docker image and deployment permissions determine what this project can actually execute.

## Revision 2 verification policy

The attached brief is a set of proposals, not a technical authority. The current query contract is [document 11](11-query-contract.md). This revision re-read official language, procedure, algorithm, indexing and command references. It did not execute database queries, install dependencies or build the application.

| Item | Current status | Still required |
| --- | --- | --- |
| Q00–Q04 and Q01R; ID indexes/constraints | Documentation-reviewed proposed text | Phase 1 execution and positive/negative semantic fixtures |
| Q05–Q10 execution transitions | Documentation-reviewed proposed text | Phase 3 query, concurrency, crash and integration evidence |
| BFS/WCC/betweenness/SPpaths/PageRank signatures | Official references reviewed | Version registration, exact casing, fixture results and justified use |
| Custom AND/OR planning | Application design | Independent expected plans and bounded-search checks |
| CCH/UDF/copy/bulk/retrieval | Documented features with adoption gates | Local capability, semantic behavior and measured product benefit |

Specific documentation findings that affect this plan:

- BFS naming differs between the procedure summary and detailed examples; record and check the local spelling. Do not silently assume case behavior.
- Constraint creation is asynchronous. An acknowledged request is not proof of an operational constraint.
- Property-existence support does not imply support for exists(graph-pattern) syntax.
- GRAPH.QUERY's version parameter concerns schema-cache mappings, not business-state concurrency.
- Graph-copy snapshots do not include external provider state. PROFILE executes its query, so a mutation profile belongs only in an isolated fixture.

Sources and exact usage are linked in document 11. If a page is unavailable or contradicts the installed behavior, keep the item unverified, inspect the pinned release's official source/release notes and resolve it before adoption. Do not fill the gap with model recollection.

## Novelty assessment

Graph-based tool selection and recovery already have prior art. The pitch must acknowledge that and focus on a well-executed contribution.

| Primary source | Relevant overlap | Consequence for Rewire |
| --- | --- | --- |
| [ToolNet](https://arxiv.org/abs/2403.00839) | Graph organization of tools and multi-hop selection | Do not claim tool graphs are new |
| [Graph-Based Self-Healing Tool Routing](https://arxiv.org/abs/2603.01548) | Rerouting around tool failures | “A graph finds another route” alone is insufficient differentiation |
| [Do Not Restart: Residual Completion for Stateful Agent Handoffs](https://arxiv.org/abs/2609.13800) | Continuing from partially completed state | Preserving useful work is also a research direction with existing work |

These are related-work pointers based on the reviewed source descriptions, not a comprehensive literature review or a reproduced comparison. Before claiming superiority over a paper, inspect its full method and run a defensible comparison.

**Our proposed distinction:** one inspectable system combining conjunctive input compatibility, effect uncertainty, graph-derived recovery and real sandbox execution, with a reviewer-controlled failure demonstration. This is an engineering contribution we can demonstrate. It is not established as a globally unique algorithm.

## Capability evidence and verification register

| Capability | Documentation source | Required project verification |
| --- | --- | --- |
| Core commands and feature map | [FalkorDB documentation index](https://docs.falkordb.com/llms.txt) | Record pinned image, module and client versions |
| Query execution and parameters | [GRAPH.QUERY](https://docs.falkordb.com/commands/graph.query) | Parameter binding, timeouts and revision protocol |
| Algorithms and introspection | [Procedures](https://docs.falkordb.com/cypher/procedures) | Enumerate and execute selected procedures |
| Custom JavaScript functions | [UDFs](https://docs.falkordb.com/udfs/) | Load versioned library and establish compatibility parity |
| Vector candidate search | [Vector indexes](https://docs.falkordb.com/cypher/indexing/vector-index) | Verify embedding dimensions, metric and candidate recall |
| Weighted route lookup | [CCH](https://docs.falkordb.com/cypher/indexing/cch-index) | Build/query/update a representative weighted network |
| Graph snapshots | [GRAPH.COPY](https://docs.falkordb.com/commands/graph.copy) | Confirm snapshot behavior and branch isolation |
| Bulk loading | [Official bulk loader](https://github.com/FalkorDB/falkordb-bulk-loader) | Verify loader/image compatibility and measure import |

No executable capability test was run while writing this plan. Prior local command discovery from the wider project is not a substitute for correctness checks on the image pinned for Rewire. Docker, self-hosted and cloud environments must each be assessed for version, permissions, supported commands and operational limits.

## Important distinctions

### RedisGraph lineage

FalkorDB's lineage makes older work useful background. It does not guarantee that an old API, algorithm implementation or configuration is supported unchanged. Prefer the current supported feature and inspect existing extensions before porting code. A proposed port must have a specific unmet requirement and a compatibility/license review.

### CCH, UDF and GRAPH.BULK

These are different mechanisms: weighted path indexing, custom query logic and data ingestion. Rewire gives each a separate adoption gate. None is a universal substitute for the planner or execution protocol.

### Database performance versus product performance

Fast traversals may help candidate discovery, but model calls, network latency, constraint evaluation and search branching can dominate. Measure the whole pipeline and attribute improvements to the stage that actually changed.

### Graph reasoning versus graphical presentation

A dependency diagram is a view. The operational contribution comes from queries and constraints changing tool selection and execution. The evidence must connect the two.

## Decision log

| Decision | Reason | Revisit when |
| --- | --- | --- |
| Select Rewire | Strong, inspectable graph-to-action demonstration | Evidence shows the core cannot be made reliable |
| Use synthetic fulfillment | Reproducible effects and faults without restricted data | A licensed public integration adds clear value |
| Separate provider world store | Makes observation-versus-reality failures genuine | External sandbox providers replace the simulator |
| One coordinator initially | Clear authority and restart behavior | Measured scale requires distributed scheduling |
| AND/OR planning with exact bindings | Multiple simultaneous prerequisites and resource effects | A formal solver provides measured benefit |
| LLM selects within validated options | Real agent behavior with enforceable contracts | Evaluation supports a broader controlled role |
| UDF after reference validator | Centralizes proven logic rather than hiding it | Local runtime support or performance is insufficient |
| CCH as routing extension | Correct mathematical fit for weighted routes | A real repeated-routing workload is added |
| No arbitrary tool onboarding | Hidden API semantics undermine safe composition | Adapter generation has independent validation evidence |
| No win probability | Competitor quality and judging are unknown | Even later evidence is unlikely to justify a precise probability |

## Main risks and concrete responses

| Risk | Response |
| --- | --- |
| Looks like ordinary retry logic | Show a replacement requiring extra prerequisites and an unseen catalog change |
| Looks like a scripted animation | Drive UI from server events and let a reviewer change faults |
| Overclaims novelty | Cite overlapping research and present the actual contribution |
| Graph becomes decorative | Store operational relationships in FalkorDB and enforce failure on graph unavailability |
| Too many features obscure the result | Require a measurable job for each advanced capability |
| Search explosion | Bound expansion, expose truncation and evaluate realistic branching |
| Uncertain external effects are mishandled | Durable intent, logical effect fencing and authoritative reconciliation |
| Polished demo hides limitations | Include blocked/unknown outcomes and publish evaluation failures |

## What would make this project unusually convincing

A reviewer can interrupt a run after a real side effect, inspect the graph, change a tool's availability, and see the system recover or stop for a concrete reason. The final result is backed by independent provider records. The authors can explain every dependency, query and limitation. That is the standard this plan is designed to reach.
