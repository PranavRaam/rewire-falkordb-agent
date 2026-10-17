# 8. Evaluation, demonstration and submission

## What earns credibility

A convincing project demonstrates the difficult case, then lets a reviewer inspect or vary it. Visual polish helps explain the result; actual effect records establish that it happened.

The evaluation must reward task completion as well as avoiding duplicates. A system that blocks every action can achieve zero duplicate bookings while being useless.

## Dataset plan

### Primary dataset: authored and generated synthetic environments

Create versioned fixtures for tool contracts, orders, resources, provider rules and faults. Use fictional IDs, zones and prices. Do not introduce personal contact details, real customer records or restricted documents.

Each fixture manifest records its seed, generator version, goal, initial world snapshot, catalog revision, fault configuration and expected observable properties. Oracle expectations live in the evaluation layer, not in the agent's prompt or plan selector.

Start with readable fixtures, then generate families that vary dependency depth, branching, unavailable producers, shared resources, expiry and ambiguity. Separate development fixtures from held-out compositions. Randomized IDs alone are insufficient evidence of generalization; change actual capability relationships and constraints.

### Optional public extension: ToolHop

[ToolHop](https://huggingface.co/datasets/bytedance-research/ToolHop) provides multi-hop tool-use tasks and executable tool implementations. Its dataset card distinguishes the data's CC BY 4.0 license from the code's Apache 2.0 license. Preserve attribution and license notices for the portions used.

Import a documented subset only after checking its schemas and execution requirements. Keep each task's catalog isolated. Any added failure injection, stateful effects or modified scoring creates a Rewire adaptation, not an official ToolHop score. This extension complements the transactional simulator; it does not replace it.

## Protocol cases

| Case | What must be established |
| --- | --- |
| Normal execution | Correct goal completion and receipts |
| Definite provider outage | Alternative path without repeating valid reservation |
| Missing one AND input | Dispatch rejected even though a graph path exists |
| Wrong order/warehouse binding | Same artifact type does not bypass identity constraints |
| Expired reservation/quote | Revalidation blocks stale inputs |
| Response lost before execution | Reconcile according to provider contract |
| Response lost after commit | Discover existing booking; no replacement effect |
| Status temporarily unavailable | UNKNOWN persists; bounded reads; no conflicting action |
| Malformed successful mutation response | Output invalidity does not imply no effect |
| Crash at each intent boundary | Recover from durable state and provider evidence |
| Repeated execute request | Same request returns existing operation/result |
| Concurrent attempts for one goal | At most one permitted logical effect |
| Resource changes between validation and call | Provider atomically rejects stale preconditions |
| Catalog/plan revision changes | Stale selection rejected and replanned |
| Cyclic or impossible catalog | Bounded search with accurate termination reason |
| Graph outage or truncated query | No silent planning or mutation from incomplete state |
| No idempotency/status support | Explicit unresolved outcome rather than false guarantee |

These are planned checks, not results. Publish failures discovered during implementation and the fixes or remaining limitations.

## Fair baselines

| Variant | Purpose |
| --- | --- |
| Bounded retry | Establish behavior of retrying the original route within a fixed policy |
| Prompt-only tool agent | Same model, contracts, provider tools and budget; no graph planner |
| Rewire without graph-based plan expansion | Measure benefit of dependency expansion while retaining action safeguards |
| Full Rewire | Graph discovery, planning, binding validation and reconciliation |

All variants get equivalent initial information, provider status capabilities, idempotency support and resource budgets. Do not disable reconciliation for a baseline to manufacture a win. Shared execution gates should remain enabled; report attempted invalid actions separately from effects prevented by those gates.

“Shared gates” means equivalent validation policies, not secretly giving the no-graph variant Rewire's graph planner. The true no-graph baseline receives flat contracts and its own operation ledger, and implements the same effect/identity checks without FalkorDB queries. Keep it confined to the evaluation harness; Rewire's production planner and operational state remain graph-backed. If a comparison retains FalkorDB-backed execution checks, label it a planner ablation rather than a fully no-graph system.

Use a fresh equivalent world snapshot for every variant. Report model/tool call budgets, prompts, search configuration and any retrieval differences. An ablation must state exactly what was removed and what remained.

## Metrics

| Metric | Definition |
| --- | --- |
| Goal completion | Independent world state satisfies every requested condition |
| Duplicate effects | Number of extra committed bookings for one logical goal |
| Correct handling of unknown outcomes | Required uncertainty preserved until authoritative resolution |
| Invalid action attempts | Requests rejected for missing/stale/conflicting prerequisites |
| Reuse | Eligible pre-existing artifacts actually retained; state denominator explicitly |
| Additional provider work | Read and mutating calls after the injected fault, reported separately |
| Recovery latency | Fault observation to validated outcome; unresolved runs reported separately |
| Cost | Observed provider cost plus model usage, with assumptions and date |
| Search behavior | Expanded states, depth, limits reached and candidate coverage |
| Explanation coverage | Executed steps with valid input and receipt provenance |

Measure graph query time separately from agent and provider latency. For repeated runs, publish counts and distributions with uncertainty where supported; small-sample percentages should not be presented as precise population estimates.

Do not claim state-of-the-art performance from synthetic scenarios alone. The useful claim is a reproducible improvement under the disclosed conditions, if the results support it.

## Scale experiments

Use controlled catalog sizes such as 100, 1,000 and 10,000 tool revisions, provided the generated data remains meaningful. Keep dependency depth and branching measurable. Record loading time, graph size, retrieval recall, expansion time, memory and end-to-end latency.

Evaluate UDF parity and overhead; compare ordinary versus bulk ingestion; compare route queries with and without CCH only on a routing workload. Include update cost and index build cost. These are distinct experiments, not a single favorable benchmark number.

## Demonstration sequence

The following script totals exactly three minutes. It is a presentation structure, not a promise that network/model calls always finish on cue. Use measured runs, edit transparently, and label replay footage.

| Time | Screen and action | Narration / evidence |
| --- | --- | --- |
| 0:00–0:15 | Show a booking with a lost response | “The shipment was booked, but the response disappeared. Did it fail—or would retrying create another shipment? Rewire checks the evidence, finds a valid recovery in FalkorDB, and shows why each next action is allowed.” |
| 0:15–0:30 | Reset to a labeled fresh scenario; show goal and R81 | Explain the 8 kg, budget and cutoff constraints; reservation already exists |
| 0:30–0:55 | Disable A; click Recover | Graph expands B's pickup, quote and label requirements; C rejected for weight |
| 0:55–1:15 | Click decision → query trace → binding | Show executed query and concrete R81/version/expiry; future price remains unknown until quote |
| 1:15–1:40 | Activate post-commit response drop for B dispatch | Provider commits; UI shows UNKNOWN; agent calls status instead of another dispatch |
| 1:40–1:55 | Open receipt and independent outcome audit | One actual booking, linked goal and settled reservation; state assumptions |
| 1:55–2:15 | Preview “B unavailable” on an analysis branch | Show alternative prerequisites or explicit no-backup result; branch cannot execute |
| 2:15–2:35 | Open measured baseline comparison | Present real success/reuse/call figures; acknowledge where both systems behave equally |
| 2:35–2:50 | Scrub replay to uncertainty and reopen evidence | Recorded mode visible; explain observation history is not provider rollback |
| 2:50–3:00 | Final graph-to-action summary | “The graph selects the recovery; contracts gate the action; receipts establish what happened.” Repository/setup link |

The live judge variation changes a catalog capability or expiry, not merely the animation. Keep a new-run preset ready, with the injection point visible.

Keep a recorded replay available for infrastructure failure, clearly labeled. Do not pretend replay is a live run. A backup replay is presentation resilience, not performance evidence.

## Blog outline

Working title: **A timeout is not a failed action: building Rewire with FalkorDB.**

1. Open with the lost shipment response and the two possible world states.
2. Explain the graph model using one small annotated diagram.
3. Show why a shortest path misses conjunctive requirements; walk through actual producer/binding queries.
4. Explain durable intents, stable operation keys and authoritative receipts; state the provider assumptions.
5. Show a query trace and one counterfactual branch with its limitations.
6. Describe the documentation-to-runtime verification process, including any discovered mismatch.
7. Publish the fair comparison, including cases where the graph adds no benefit.
8. Explain which FalkorDB features shipped and why unused algorithms were omitted.
9. Link reproducible setup, fixture/evaluation manifests, repository and video; disclose AI assistance and related work.

Use actual screenshots and results from the finished build. Never write the benchmark conclusion before running it.

## Questions a judge should be able to answer

- What changed in the graph that changed the agent's action?
- Which queries found the alternative, and which condition rejected another?
- How do we know the booking was actually created?
- Why did the agent reconcile instead of booking again?
- What happens if status information cannot be obtained?
- What breaks if FalkorDB is unavailable?
- How much logic is general and how much belongs to provider adapters?
- Which advanced features improved a measured workload?

## Submission package

- Public repository with original-work history and third-party attribution.
- README with complete setup, pinned versions, environment variables and exact demo steps.
- Graph model diagram and the named Cypher queries/algorithms actually used.
- Working demo video and deployment, or complete local setup instructions.
- Explicit Track 01 entry and AI-assistance disclosure.
- Dataset manifest and license notes.
- Evaluation manifest and measured results; no placeholder metrics.
- Known limitations and clear shipped-versus-roadmap distinction.

Check the organizer's current [rules and submission guidance](https://www.wemakedevs.org/hackathons/falkordb) before submitting. The planning scope here does not change the event's submission deadline.
