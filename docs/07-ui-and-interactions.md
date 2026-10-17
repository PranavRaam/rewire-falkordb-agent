# 7. UI and interactions

## Design objective

Make a complicated recovery understandable in ten seconds and inspectable in two minutes. The interface should answer: what was requested, what broke, what remains valid, what will happen next, and how do we know it finished?

This is an operational product, so the primary screen is an active run. A marketing landing page is unnecessary for the main demonstration.

## Main workspace

~~~text
┌──────────────────────────────────────────────────────────────────────────────┐
│ REWIRE     Order O-104 · Replacement motor    LIVE · Synthetic environment    │
│ Goal: one shipment · 8 kg · ≤900 units · before 16:00       Status: Recovering │
├─────────────────┬───────────────────────────────────────┬────────────────────┤
│ Runs            │ Workflow                              │ Decision inspector │
│ O-104           │                                       │                    │
│                 │ Stock → R81 ───────────────┐          │ Why Carrier B?     │
│ Views           │           Carrier A ×     │          │ Preserves R81      │
│ Execution       │ W7 → Pickup → Quote → Label → B      │ Quote: 760 units   │
│ Capabilities    │                                       │ C: weight exceeded │
│ Evidence        │ Proposed / confirmed / unknown legend │ Evidence links     │
│                 ├───────────────────────────────────────┤                    │
│ Demo controls   │ Event timeline                       │ Next allowed step  │
│ Failure point   │ 15:21 reservation verified           │ Reconcile dispatch │
│ Response drop   │ 15:22 dispatch outcome unknown       │                    │
├─────────────────┴───────────────────────────────────────┴────────────────────┤
│ [Recover workflow] [Pause scheduling]   Provider outcome: not yet confirmed   │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

The diagram is a proposed layout, not a screenshot or a statement that the interface exists.

## Screen and component specification

### 1. Run overview

Show the goal in ordinary language, constraints as compact labels, current state, graph revision, last event time and live/replay mode. Show a clear banner for UNKNOWN outcomes. Keep the current task and result visible while the user inspects details.

Primary action changes by state: Start workflow, Recover workflow, Reconcile outcome, or View result. Disable actions with an explanation when blocked. Do not offer “Retry booking” while the booking outcome is unresolved.

### 2. Workflow graph

Render the selected run's execution graph, not the entire database. Use stable positions across updates so the user can follow the change. Proposed steps have dashed borders; confirmed steps use a completion icon; blocked/unknown states have distinct icons and text, not color alone.

Preserved artifacts remain in place. Repair steps appear on an adjacent branch. Selecting an artifact highlights its producing attempt and consuming steps. Selecting a step highlights all required inputs. A label such as “4 of 4 requirements satisfied” opens the exact bindings.

Offer a separate capability view for the tool/type graph. Keep abstract possibilities separate from actions that were actually executed.

### 3. Candidate comparison

| Candidate | Eligibility | New work | Cost | Reason |
| --- | --- | --- | --- | --- |
| Carrier A | Unavailable for current attempt | — | — | Authoritative no-effect result |
| Carrier B | Valid after prerequisite completion | Pickup, quote, label, dispatch | 760 observed quote | R81 remains reusable |
| Carrier C | Rejected | — | Not actionable | 5 kg maximum versus 8 kg package |

Populate the table from backend records. Before a quote exists, show “unknown” or an explicitly labeled estimate. Never present the illustrative 760 value as observed before the quote call.

### 4. Decision inspector

Start with a short explanation, then expand into conditions, bindings, queries and receipts. Every evidence link should navigate to a concrete record. Show the time and revision of each observation.

Useful tabs: Why this action, Required inputs, Rejected alternatives, Query evidence, Provider response. Sanitized query details may show the named query and parameters; ordinary users should not need to read Cypher to understand the result.

### 5. Live event timeline

Show actual events with timestamps and durations. Distinguish proposed plan, attempted call, observed response and confirmed effect. Expand an unknown outcome to show reconciliation attempts and what remains missing.

Event stream interruptions show a reconnecting indicator. They do not imply that execution stopped. Resume from the event cursor without duplicating rows.

### 6. Outcome audit

Show the requested conditions and the evidence establishing each one: booking ID, order match, price, provider state and settled reservation. In demonstration/evaluation mode, include a separately labeled provider-world audit showing committed booking count.

This audit view must not be fed back into the agent as privileged knowledge. The ordinary agent must obtain its evidence through registered provider tools.

### 7. Failure controls

A collapsed demo drawer lets the presenter choose outage-before-execution, lost-response-after-commit, reservation expiry or invalid label. It displays the precise injection point and active fault.

Controls alter the simulator, not graph colors. New experiments create new runs. Label all fixtures and synthetic data. Prevent edits that would change a completed run's historical evidence.

### 8. Snapshot comparison and replay

Compare source and proposed branch with changed steps, reused artifacts and estimated incremental cost. Snapshots are visibly non-executing. Replay has a persistent recorded-mode label and timeline scrubber; no button on a replay may invoke a provider.

### 9. Exact query trace

Add a Query trace tab alongside Decisions. Selecting a decision filters its query calls. Each row shows query ID/hash, graph revision, sanitized bound parameters, start time, elapsed time, result count and truncation/error status. Expand to show the exact executed Cypher and returned records. Highlight the node IDs used by the decision in the graph. Application predicates appear as separate validation rows with rule version and inputs; do not disguise them as database results.

### 10. Counterfactual failure preview

On a tool node, choose “What if unavailable?” Create an isolated analysis snapshot with a visible source revision. Disable the capability in the branch and replan. Show preserved work, added steps, missing conditions and whether the search was complete. “No backup found within search budget” must remain distinct from “no backup exists in this model.” Closing the branch never changes provider state. Executing a chosen alternative requires fresh validation against the live run.

### 11. Fair comparison panel

Choose a completed scenario and compare Rewire with a no-graph agent on equivalent starting snapshots. Show measured outcomes and tool calls side by side. If both avoid a duplicate, show that. Highlight the source of any difference: dependency discovery, binding validation, redundant work or latency. A deliberately unsafe retry example can be labeled a failure illustration, but is not the primary benchmark opponent.

### 12. Resilience inspector

Show BFS impact candidates and WCC islands in analysis mode. Optional centrality results are labeled structural heuristics. Clicking “Check whether essential” runs explicit removal-and-replan analysis. Do not use a red “single point of failure” badge solely because a centrality score is high.

## Visual system

- Use a restrained charcoal, warm-white and teal palette, with amber for uncertainty and red for invalid/failed states.
- Prioritize readable body text, monospaced IDs, consistent spacing and compact tables.
- Use an 8 px spacing rhythm, modest corner radii, clear borders and a limited elevation scale.
- Use motion only to orient attention to a changed step; respect reduced-motion preferences.
- Avoid animated decorative networks, invented confidence percentages and crowded KPI panels.
- Use locally bundled or appropriately licensed fonts and icons; record attribution.

Proposed color tokens: canvas #0F1720, panel #17222D, text #F4F5F6, muted #ABB8C4, accent #43D9B3, warning #F2BA63, danger #F2777A. Check contrast in the implemented combinations rather than assuming these values guarantee accessibility.

## Responsive behavior and accessibility

Desktop uses the three-column layout. Medium screens collapse navigation; small screens show ordered panels with a toggle between graph and timeline. The essential decision explanation must remain usable without interacting with a graph canvas.

Every graph selection has a keyboard-accessible list/table alternative. Maintain focus when panels update, label icon buttons and announce important status changes without announcing every event. Provide loading, empty, disconnected, unavailable and blocked states explicitly.

## UI acceptance criteria

1. A new reviewer can identify the goal and failure without narration.
2. Clicking the final result leads to the actual action and provider evidence.
3. A proposed step never looks confirmed before the provider outcome is known.
4. Unknown outcomes remain visibly unresolved across refresh and reconnect.
5. Every number identifies whether it is observed, estimated or illustrative.
6. The main recovery is understandable without zooming around a huge graph.
7. Live and replay modes cannot be confused.
8. The interface works with keyboard navigation and reduced motion.
