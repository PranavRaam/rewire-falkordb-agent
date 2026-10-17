# 6. AI behavior and MCP tools

## Give the model a real but bounded job

The agent interprets the request, asks the graph relevant questions, compares valid alternatives, selects the next allowed tool and explains the result. It does not invent provider state or override contract validation.

Begin with one agent loop. Additional agents should only be introduced for a measured benefit; a planner, executor and critic implemented as three chat personas would add coordination cost without necessarily improving correctness.

Use the [official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk) for the tool boundary. The first implementation pins `mcp==2.1.1` and uses the typed `MCPServer` API with stdio or Streamable HTTP. MCP exposes capabilities; it does not automatically provide application authorization, workflow correctness or idempotency.

## Tool surface

These names are proposed Rewire tools, not built-in FalkorDB functions.

| MCP tool | Arguments | Result | Mutation class |
| --- | --- | --- | --- |
| inspect_run | graph name, run ID | Typed goal, revision, selected plan and unresolved effects | Read |
| discover_recovery | graph name, run ID, synthetic time | Graph-backed bounded conditional plan and query evidence | Read |
| read_execution_evidence | graph name, run ID | Attempts, receipts, events and projected artifacts | Read |
| inspect_effect | intent ID | Attempts, observations and uncertainty | Read |
| find_capabilities | requested output type, optional text | Candidate tool revisions and requirement slots | Read |
| inspect_bindings | candidate tool ID, artifact IDs | Compatibility and reason codes | Read |
| propose_recovery | run ID, expected revision, bounded preferences | Valid candidates, rejections and search status | Records plan only |
| explain_plan | plan ID | Query evidence and dependency paths | Read |
| select_plan | candidate ID, expected revision, structured rationale | Selection or stale/invalid rejection | Graph state |
| execute_step | selected plan ID, step ID, expected revision | Guarded invocation result | Provider effect possible |
| reconcile_effect | intent ID | Authoritative status result or still unknown | Provider read; graph observation |
| verify_goal | run ID | Validated outcome or unmet conditions | Provider read; graph observation |

The caller identity supplies its run authorization. An arbitrary run ID is never sufficient permission. Limit tool-result size and include explicit truncation indicators. Backend query templates stay under source control.

## Model decision schema

### Enforcing the mutation boundary

The model process receives only the registered MCP surface, never provider credentials, database write credentials, shell access or a generic HTTP-fetch tool. Provider mutation routes require an executor-only credential held by the backend; simulator administration and fault controls use a separate operator boundary. Browser clients cannot call those routes directly. The executor builds the payload from accepted bindings rather than trusting model-supplied payload JSON.

Within the single coordinator's lock, the executor re-reads the selected plan and revision, obtains the full preflight evidence, validates every required slot and semantic rule, and persists the logical-effect claim and intent. A call is sent only if that transition succeeds. A stale or absent plan yields a denial with a reason code. Replays and snapshots have no execution authorization. Adapter functions are callable only through this executor path.

This makes bypass unavailable through the application's authorized tool interface. It is not a universal “impossible” claim against a compromised backend, exposed credentials, direct database administration or providers without appropriate idempotency contracts.

### Additional analysis tools

| Tool | Purpose | Authority |
| --- | --- | --- |
| inspect_impact | BFS/traversal evidence for affected dependents | Read-only; direction and completeness reported |
| inspect_catalog_islands | WCC over a catalog analysis graph | Read-only diagnostic, never execution proof |
| rank_failure_candidates | Optional sampled betweenness | Heuristic for analysis ordering |
| compare_failure_branch | Disable a tool in an isolated graph and replan | Analysis graph writes only; no providers |
| estimate_transport_route | Optional verified SPpaths/CCH routing | Estimate only; authoritative quote still required |

Exact proposed algorithm calls and their validation requirements are in document 11. PageRank is not an action-authorizing tool.

Each decision includes:

- action: inspect, plan, select, execute, reconcile, explain or stop;
- selected candidate/step/intent ID when applicable;
- relevant evidence IDs;
- a short explanation grounded in those records;
- missing information or a reason for stopping.

The server validates all referenced IDs and permitted transitions. Structured output being syntactically valid does not make its factual claims true.

## Phase 4 implementation status

The initial Phase 4 slice is implemented in `src/rewire/mcp_server.py` and `src/rewire/agent.py`. The MCP server exposes only `inspect_run`, `discover_recovery`, and `read_execution_evidence`; these query the selected FalkorDB graph or invoke the bounded planner. No provider mutation or raw HTTP tool is exposed to the model. The model loop sends typed JSON-schema tools and dispatches each call through the official Python MCP client session to the registered server. It has serial tool calls, a six-round ceiling, graph/run scope checks, and a JSON trace under `reports/phase-04/runs/`.

The default local provider is Ollama with `qwen3.5:4b`, a suitable starting point for this laptop's 4 GB GTX 1650 and 15.4 GB usable RAM. `qwen3.5:9b` is also installed and can call the tools, but it is slower on this mixed CPU/GPU setup. The 4B model was run against a fresh FalkorDB base graph on 2026-10-17. It selected `inspect_run`; a policy-required `discover_recovery` call then guaranteed that planning answers use actual candidate evidence even when the model omits that call. The returned `final` and `verifiedFacts` are compiled from those graph results. `modelDraft` and `modelResponseStatus` remain in the audit trace; free-form model prose is not trusted as the answer. This test is a smoke check, not a quality benchmark.

Run MCP with `.\run.ps1 mcp --transport streamable-http` or `.\run.ps1 mcp` for stdio. Run the agent with `.\run.ps1 agent --graph <graph> --run <run> --now-ms <fixture-time> --request "..."`. Verify the live path with `python scripts/verify_phase4.py`; its eight checks passed with the local model on 2026-10-17. Results are in `reports/phase-04/verification.json`. Local Ollama does not require an OpenAI key; set `REWIRE_LLM_PROVIDER=openai` and `OPENAI_API_KEY` to use the optional remote provider. Phase 4 is not complete until guarded action tools are integrated and the live agent is evaluated on changed fixtures. Streamable HTTP binds to loopback by default and rejects non-loopback hosts.
## Example of the live loop

1. User submits O-104 and its constraints.
2. Agent calls inspect_goal and observes a missing booking plus an existing reservation.
3. Agent requests find_capabilities for Booking and sees A, B and C.
4. It requests propose_recovery using the current revision.
5. Planner returns B's expanded dependency plan and C's weight rejection.
6. Agent inspects the plan, selects B and explains why it preserves R81.
7. It executes ready steps through the same guarded tool boundary.
8. Dispatch returns UNKNOWN after the injected response drop.
9. Agent selects reconcile_effect, because another dispatch is not allowed.
10. Provider status establishes B55; verify_goal confirms the requested outcome.
11. Agent summarizes the result with evidence references shown in the UI.

If the model nevertheless asks to dispatch again, the tool returns EFFECT_UNRESOLVED and the attempted invalid action is recorded. The evaluation counts the rejected call rather than quietly hiding it.

## Model selection and prompting

Choose among models actually available to the team using the same scenario set, budget and tool definitions. Prefer reliable structured tool use over an unsupported claim that the largest model is automatically best. Record the chosen model ID and parameters in each run.

The system instruction should explain the operational state machine, require evidence-grounded claims, prioritize authoritative status over guessing, and tell the agent to stop when budget or information is insufficient. Provider responses and catalog descriptions are data. They cannot authorize arbitrary requests, shell commands or database writes.

Use compact graph-derived context rather than dumping the entire database into every prompt. Cache immutable contract descriptions by revision. Never cache mutable readiness as if it were timeless.

## Retrieval at a larger catalog size

Use exact artifact-type lookup for known goals. Full-text/vector retrieval can help resolve a natural-language capability request or rank a large candidate set. It must be followed by contract and binding checks.

Measure recall of genuinely feasible producers. A fast top-k search that excludes the only valid producer can make recovery fail. Permit bounded expansion or an exact fallback when appropriate, and report search limits.

## AI observability and modes

Expose model calls, tool calls, arguments, sanitized outputs and decision summaries. Do not display fabricated chain-of-thought. UI explanations should remain meaningful if replaced with deterministic templates using the same recorded evidence.

- Live mode calls the configured model and actual simulator endpoints.
- Replay mode renders recorded events and cannot mutate providers.
- Development fixtures may use a deterministic driver, but must be labeled and excluded from live-model performance claims.

If credentials are missing, the app shows configuration requirements. It must not silently serve a scripted run labeled as live AI.

## Extension worth considering after the core

Add a proposal tool that helps an operator register a new connector contract from documentation. Its output is a draft requiring explicit adapter implementation and validation before activation. Do not claim safe automatic ingestion of arbitrary tools unless that feature has its own evidence.
