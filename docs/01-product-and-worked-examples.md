# 1. Product and worked examples

## The problem in ordinary language

A software agent often needs several tools to finish one job. Some tools read information; others reserve stock, create a booking or publish a result. If the fifth step fails, starting again can repeat actions that already succeeded. Simply changing tools may also fail because the replacement expects different inputs.

Rewire asks four questions:

1. What must be true when this job is finished?
2. What has already happened, and what remains usable?
3. Which connected capabilities can satisfy the remaining requirements?
4. What evidence permits the next action?

This matters in fulfillment, report generation, provisioning and other multi-service workflows. The submitted product uses a synthetic fulfillment environment so the entire chain is reproducible without real customers, shipments or purchases. The examples below are illustrative scenarios, not claims about named companies or actual incidents.

## Intended user and value

The user is an operator supervising tool-using agents. Today they inspect logs, identify the last reliable state and manually decide whether to retry. Rewire makes that decision inspectable and executes a bounded recovery where the tool contracts provide enough information.

The first product is deliberately for registered, understood tools. It does not promise to safely compose arbitrary websites or infer every hidden API rule from prose.

## Example A — A replacement shipment after a carrier outage

### Requested outcome

“Create one shipment for order O-104: one replacement motor, 8 kg, from an eligible warehouse to synthetic zone Z3, for at most 900 cost units, before the 16:00 cutoff.”

Successful completion requires a confirmed booking linked to this order, its label, and exactly one settled inventory reservation. The reservation moves from HELD to CONSUMED when dispatch succeeds. A held reservation alone is not completion. Costs and zones are synthetic and visibly labeled.

### Starting facts

| Record | Fact |
| --- | --- |
| Order O-104 | Item M-8, quantity 1, weight 8 kg, destination Z3 |
| Warehouse W7 | Sufficient stock; eligible origin |
| Reservation R81 | HELD for O-104 at W7; version 1; expires 15:40 |
| Carrier A | Direct booking tool; current attempt returns authoritative unavailable-before-execution |
| Carrier B | Dispatch requires a reservation, pickup identifier, eligible quote and label |
| Carrier C | Cheaper service, but maximum package weight is 5 kg |
| Current simulated time | 15:20 |

The demo catalog contains approximately 15–25 meaningful tools: lookup, reservation, provider status, pickup resolution, quotes, labels, dispatch and outcome inspection across alternatives. Final quantity follows the fixture design; tool IDs and descriptions can be permuted.

### What the graph lets the agent discover

The missing goal is a Booking. Carrier B can produce one, but it needs several inputs simultaneously:

~~~mermaid
flowchart LR
  W[Warehouse W7] --> P[Resolve pickup]
  P --> PI[Pickup ID]
  PI --> Q[Get eligible quote]
  O[Order O-104] --> Q
  Q --> QT[Quote: 760 units]
  QT --> L[Create label]
  O --> L
  L --> LB[Label for O-104 / W7]
  R[Existing reservation R81] --> D[Dispatch through B]
  PI --> D
  QT --> D
  LB --> D
  D --> B[Confirmed booking]
~~~

The graph stores both these capabilities and their constraints. A path to dispatch is insufficient: all incoming requirements must be satisfied with mutually compatible records. A label for a different warehouse is not interchangeable just because it has the same type.

### Actual recovery sequence

1. Record A's authoritative no-effect result. A timeout alone would not establish this fact.
2. Find the unmet Booking goal and traverse candidate producer tools.
3. Preserve R81 because the provider confirms it is still HELD and unexpired.
4. Reject C because 8 kg exceeds its 5 kg contract limit. Record the comparison as evidence.
5. Resolve W7 to B's pickup identifier.
6. Obtain B's quote and verify price, zone, weight, expiry and cutoff.
7. Produce and validate the matching label.
8. Validate the complete binding set and write a durable dispatch intent.
9. Dispatch with a stable operation key. The simulator consumes R81 and creates booking B55 atomically in its own database.
10. Read provider status and verify the requested outcome before declaring success.

### What the senior reviewing the project sees

The failed A step remains visible. The preserved reservation stays highlighted. New B steps appear as a proposed branch, then change state only as actual events arrive. Clicking C explains its rejection. Clicking the final booking shows the provider receipt, operation key, reservation and goal it satisfies.

## Example B — The booking happened, but the answer disappeared

This is the strongest variation of Example A. At step 9, the provider commits B55 and the network response is deliberately dropped.

| Perspective | State |
| --- | --- |
| Provider world | B55 exists; R81 is CONSUMED |
| Agent observation | Dispatch outcome UNKNOWN |
| Correct next action | Query B's authoritative operation-status endpoint |
| Forbidden shortcut | Start a new booking with B or switch to C while B's outcome is unresolved |

Rewire persists UNKNOWN, calls status with the original key, receives B55, validates it, and completes the goal. The final world audit shows one booking and one consumed reservation. No new booking call is necessary.

If status is temporarily unavailable, it performs bounded read-only reconciliation attempts. If the provider cannot support idempotency or authoritative reconciliation, Rewire pauses with an unresolved outcome. The UI must not turn this into either success or a definite failure.

The general distinction between an error response and certainty about side effects is reflected in [Stripe's low-level error guidance](https://docs.stripe.com/error-low-level). Rewire's simulator demonstrates our own explicit contract, not Stripe integration.

## Example C — A previously useful reservation expires

Move the simulated clock past 15:40 before dispatch. R81 now fails the readiness check even though its shape and order ID are correct.

The agent asks the inventory provider for authoritative status, marks the old reservation unusable and finds a new reservation path. If W7 still has stock, it obtains R82. If only W9 has stock, the warehouse binding changes: the W7 pickup, quote and label cannot be reused without their contracts explicitly allowing it. FalkorDB identifies the dependent plan steps and the planner rebuilds only the affected branch.

If no stock is available, the correct result is BLOCKED with a concrete unmet requirement. The system does not hallucinate availability to make the demo end green.

## Example D — HTTP success, semantically wrong result

The label tool returns HTTP 200, but its response describes a 0.8 kg package or warehouse W9. Schema validation can succeed while the business meaning is wrong.

Rewire compares the returned artifact against O-104 and the bound quote. It records INVALID_OUTPUT, keeps the raw response digest and validation details, and prevents dispatch using that label. A registered alternative label producer may satisfy the goal; otherwise the system reports the exact inconsistency.

This is why the product needs typed graph bindings and semantic validators in addition to a successful HTTP status.

## Example E — Generality without another large application

After the fulfillment core works, add a small synthetic reporting catalog: fetch public-style sample rows → transform → render → publish to a local artifact directory. Disable the preferred renderer. A replacement needs a different intermediate format, so the planner discovers an additional conversion step and preserves the valid input dataset.

Use the same planner and execution protocol, with new contracts and adapters. Publishing has an operation key and a receipt. If this requires hardcoding a new fallback planner, the generality claim has failed. This extension supports the architecture; fulfillment remains the main demo.

## What we can responsibly claim

“Rewire composes and executes recoveries for registered tools using graph dependencies, validated artifacts and explicit effect tracking.”

We cannot yet claim universal workflow repair, guaranteed exactly-once effects across arbitrary providers, first-ever graph recovery, or better performance than competitors. Those require evidence or stronger assumptions than this plan provides.
