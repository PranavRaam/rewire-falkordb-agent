# 10. Revised judge's-eye plan

This revision responds to the supplied brief without accepting its technical suggestions as facts. Solo builder; specified stack; no hour-based cuts. Every feature needs a visible demo, UI or README contribution. Phase 1 is the only build prompt supplied.

## Honest assessment

**Concept score: 7/10 today.** This is my subjective assessment of the proposal, not an official judging rubric, an assessment of unbuilt software or a winning probability.

| Dimension | Assessment |
| --- | --- |
| Track fit | Strong: graph-derived selection followed by observable action |
| Originality | Moderate: tool graphs, recovery and partial-progress reuse have prior art |
| Immediate clarity | Needs work: “workflow repair” sounds like ordinary retry middleware |
| Technical substance | Strong if AND prerequisites, stale bindings and uncertain effects actually work |
| Evidence today | A plan exists; no implemented result has been established |

My inference from the [published Track 01 focus](https://www.wemakedevs.org/hackathons/falkordb) is that judges will value a clear graph-to-action chain, explainable tool selection and a working demonstration. No detailed official scoring weights were established in this research, so these are design priorities rather than invented judging criteria.

The weakness to fix is not a shortage of algorithms. It is the risk that a viewer sees a hardcoded fallback with an attractive graph. The strongest correction is a reviewer-controlled failure, a changed prerequisite chain and an exact evidence trail, followed by an honest baseline comparison.

## Reframed pitch

**Rewire uses a live capability graph to repair interrupted agent workflows, reuse valid work, and reconcile uncertain actions before attempting replacements.**

### Fifteen-second opener

“The shipment was booked, but the response disappeared. Did it fail—or would retrying create another shipment? Rewire checks the evidence, finds a valid recovery in FalkorDB, and shows why each next action is allowed.”

Do not say “it never double-acts” without stating the provider contracts and operating assumptions. The system enforces its protocol through its controlled executor; arbitrary external APIs may not provide enough evidence to guarantee an outcome.

## Maximum-impact feature order

Track abbreviations: M = multi-hop; G = graph queries/algorithms; T = MCP selection; A = actions; E = explainability.

### Core

| Priority / feature | What it does | Track | Visible proof | Main risk |
| --- | --- | --- | --- | --- |
| 1. Graph-derived recovery | Expands requirements and finds a compatible conditional plan | M G T A | B requires pickup → quote → label before dispatch | A simple path ignores AND inputs |
| 2. Guarded executor | Checks selected plan, current bindings and logical effect before mutation | G A E | Invalid call is denied with an exact condition | Check/claim race or bypass route |
| 3. Intent/receipt ledger | Separates attempted calls from confirmed effects | M A E | UNKNOWN → status lookup → existing booking | Provider lacks authoritative status |
| 4. Real failure injector | Drops response precisely after provider commit | A E | World contains a booking while agent sees UNKNOWN | Fault changes UI only |
| 5. Query and evidence trace | Links decision to exact queries, bindings and receipts | G T E | Click “Why?” and see the records | Trace omits hidden application rules |
| 6. Independent outcome audit | Checks the goal against provider truth | A E | One booking and consumed reservation | Agent receives evaluator-only oracle |

### Edge features

| Priority / feature | What it does | Track | Visible proof | Main risk |
| --- | --- | --- | --- | --- |
| 7. Counterfactual preview | Disables a tool in an analysis graph and computes conditional backups | M G E | Compare original and “this tool unavailable” plans | Snapshot mistaken for predicted external truth |
| 8. Live catalog variation | Adds a compatible producer or changes requirements without planner edits | M G T A | A different discovered chain appears | Adapter still hides the fallback |
| 9. Fair side-by-side baseline | Runs no-graph agent on the same scenario and provider contracts | A E | Actual calls, results and costs compared | Rigged baseline or fabricated duplicate |
| 10. Replay with evidence cursor | Reconstructs recorded execution observations | E | Scrub to the exact moment uncertainty began | Mistaken for provider rollback |
| 11. Scenario isolation | Independent graphs and provider namespaces per run | G A E | Two scenarios do not share artifacts | Graph names treated as authorization |
| 12. Resilience inspector | BFS impact, WCC islands and explicit removal/replan analysis | M G E | Highlight affected work and show whether a backup exists | Topology heuristic presented as feasibility proof |

### Stretch

| Feature | What it does | Track | Visible proof | Main risk |
| --- | --- | --- | --- | --- |
| Reviewed OpenAPI import | Drafts tools, slots and schema links; human supplies semantic/effect annotations | G T E | Import preview shows inferred versus reviewed fields | OpenAPI lacks enough effect/idempotency semantics |
| Compatibility UDF | Executes a validated predicate close to graph data | G A E | Same input yields same reason code as reference | Runtime differences or unsupported return shape |
| Large-catalog search and bulk load | Candidate retrieval plus reproducible ingestion experiments | G T E | README performance/recall tables | Irrelevant scale or excluded feasible tools |
| SPpaths/CCH transport estimates | Weighted route estimates in a separate routing layer | G E | Route/weight explanation next to carrier quote | Confused with workflow planning |
| Betweenness ordering | Prioritizes capabilities for removal experiments | G E | Score labeled heuristic; actual replan proves impact | Centrality mistaken for necessity |

PageRank-based “critical tool” claims and community detection are cut from the default product: no demonstrated decision benefit. Their existence in the database is not enough reason to use them. A PageRank diagnostic signature is documented for completeness, with no production tool registration planned.

## Reliability with a nondeterministic model

Seed the simulator and catalog generator; use a controlled scenario clock; freeze contract versions; sort equal candidates deterministically. These stabilize the environment, not the LLM. Even temperature zero is not a promise of identical model output.

Constrain the model to registered tools and validated IDs; cap retries/search; persist all visible decisions and tool results. Evaluate repeated live runs, including failures. Keep a labeled recorded replay for presentation recovery. Never silently replace an unsuccessful live model run with scripted output.

## Where the graph does not provide an advantage

- For a one-step stateless retry, the graph may add overhead.
- Provider idempotency prevents duplicates independently of graph storage.
- If both agents have the same operation ledger and status tools, both may reconcile correctly.
- The graph cannot invent a missing provider capability or resolve an unobservable external effect.
- A tiny fixed catalog may be handled equally well by a prompt-only agent.

Measure graph-specific gains in dependency discovery, invalid-binding prevention, reusable-work identification and explanation, rather than attributing every reliability benefit to FalkorDB.

## Top five risks

| Risk | Mitigation | Evidence |
| --- | --- | --- |
| AI-generated database fiction | Source → local capability → semantic fixture gates | Query/algorithm verification matrix |
| Apparent novelty is existing retry/routing | Multi-input changes, unknown effects and held-out catalog compositions | Live changed-scenario trace |
| Unauthorized or duplicate mutation | Restricted credentials, guarded executor, logical effect claim and provider contract | Negative-path and crash evidence |
| Baseline comparison misleads | Same tools, information, budgets and safeguards | Published manifests and failures |
| Feature sprawl obscures product | Every feature mapped to a visible payoff; separate stretch | Three-minute script and shipped feature list |

## Definition of a strong entry

A judge changes a failure; the agent discovers a different graph-backed plan; an uncertain action is reconciled; and every important claim is inspectable in a query, binding, receipt or measured result. That earns more confidence than an unsupported “state of the art” label.
