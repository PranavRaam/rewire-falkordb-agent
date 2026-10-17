"""Seeded, synthetic scenarios. No personal or external production data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from rewire.domain import Artifact, Goal, Slot, Tool, unique_nodes

BASE_TIME = datetime(2026, 10, 17, 9, 50, tzinfo=timezone.utc)
BASE_MS = int(BASE_TIME.timestamp() * 1000)
SEED = 10401
CATALOG_REVISION = 1


def ms_after(minutes: int) -> int:
    return int((BASE_TIME + timedelta(minutes=minutes)).timestamp() * 1000)


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    now_ms: int
    goal: Goal
    artifacts: tuple[Artifact, ...]
    tools: tuple[Tool, ...]
    run_id: str = "run-phase1-fixture"


def _slot(tool_id: str, name: str, type_id: str, schema: str, *,
          status: str = "READY", order: bool = False, warehouse: bool = False,
          output_bindings: dict[str, str] | None = None) -> Slot:
    bindings: dict[str, str] = {}
    if order:
        bindings["orderId"] = "orderId"
    if warehouse:
        bindings["warehouseId"] = "warehouseId"
    return Slot(
        id=f"slot:{tool_id}:{name}", name=name, type_id=type_id,
        cardinality=1, schema_version=schema, min_version=1,
        required_status=status, scope_order=order, scope_warehouse=warehouse,
        rule_id=f"rule:{type_id.lower()}:v1",
        output_bindings=output_bindings if output_bindings is not None else bindings,
    )


def _tool(tool_id: str, *, enabled: bool = True, weight: float = 0,
          output: str = "Booking", output_schema: str = "booking-v1",
          slots: tuple[Slot, ...] = (), effect: str = "READ_ONLY",
          consumes: tuple[str, ...] = ()) -> Tool:
    return Tool(
        id=f"tool:{tool_id}:v1", tool_id=tool_id, version=1,
        catalog_revision=CATALOG_REVISION, enabled=enabled,
        adapter_id=f"adapter:{tool_id}", effect_class=effect,
        max_weight_kg=weight, output_type=output,
        output_schema_version=output_schema, slots=slots,
        output_bindings={"orderId": "orderId", "warehouseId": "warehouseId"},
        consumes=consumes,
    )


def base_scenario() -> Scenario:
    goal = Goal(
        id="goal:shipment:O-104", output_type="Booking", order_id="O-104",
        warehouse_id="W7", destination_zone="Z3", weight_kg=8.0,
        max_cost_units=900, cutoff_at=ms_after(40),
    )
    artifacts = (
        Artifact("artifact:order:O-104", "Order", "order-v1", 1, "READY", 0,
                 "O-104", "W7", {"packageHash": "pkg-M8-8kg", "quantity": 1,
                                   "destinationZone": "Z3", "weightKg": 8.0}),
        Artifact("artifact:warehouse:W7", "Warehouse", "warehouse-v1", 1,
                 "READY", 0, "O-104", "W7", {"zone": "origin-W7"}),
        Artifact("artifact:reservation:R81", "Reservation", "reservation-v1", 1,
                 "HELD", ms_after(20), "O-104", "W7", {"reservationId": "R81",
                                                           "quantity": 1}),
    )
    tools = (
        _tool("carrier-a-dispatch", enabled=False, effect="EXTERNAL_MUTATION",
              slots=(_slot("carrier-a-dispatch", "order", "Order", "order-v1", order=True),
                     _slot("carrier-a-dispatch", "reservation", "Reservation",
                           "reservation-v1", status="HELD", order=True, warehouse=True)),
              consumes=("Reservation",)),
        _tool("carrier-b-pickup", output="Pickup", output_schema="pickup-v1",
              slots=(_slot("carrier-b-pickup", "warehouse", "Warehouse",
                           "warehouse-v1", order=True, warehouse=True),)),
        _tool("carrier-b-quote", output="Quote", output_schema="quote-v1",
              slots=(_slot("carrier-b-quote", "order", "Order", "order-v1", order=True),
                     _slot("carrier-b-quote", "pickup", "Pickup", "pickup-v1",
                           order=True, warehouse=True))),
        _tool("carrier-b-label", output="Label", output_schema="label-v1",
              slots=(_slot("carrier-b-label", "order", "Order", "order-v1", order=True),
                     _slot("carrier-b-label", "quote", "Quote", "quote-v1", order=True))),
        _tool("carrier-b-dispatch", effect="EXTERNAL_MUTATION",
              slots=(_slot("carrier-b-dispatch", "reservation", "Reservation",
                           "reservation-v1", status="HELD", order=True, warehouse=True),
                     _slot("carrier-b-dispatch", "pickup", "Pickup", "pickup-v1",
                           order=True, warehouse=True),
                     _slot("carrier-b-dispatch", "quote", "Quote", "quote-v1", order=True),
                     _slot("carrier-b-dispatch", "label", "Label", "label-v1", order=True)),
              consumes=("Reservation",)),
        _tool("carrier-c-dispatch", weight=5.0, effect="EXTERNAL_MUTATION",
              slots=(_slot("carrier-c-dispatch", "order", "Order", "order-v1", order=True),)),
        _tool("catalog-inspector", output="Inspection", output_schema="inspection-v1",
              slots=(_slot("catalog-inspector", "order", "Order", "order-v1", order=True),)),
    )
    unique_nodes(goal, artifacts, tools)
    return Scenario("base", SEED, BASE_MS, goal, artifacts, tools)


def with_carrier_d(scenario: Scenario) -> Scenario:
    """Add a new compatible producer chain without planner changes."""
    tools = scenario.tools + (
        _tool("carrier-d-pickup", output="PickupD", output_schema="pickup-d-v1",
              slots=(_slot("carrier-d-pickup", "warehouse", "Warehouse",
                           "warehouse-v1", order=True, warehouse=True),)),
        _tool("carrier-d-quote", output="QuoteD", output_schema="quote-d-v1",
              slots=(_slot("carrier-d-quote", "order", "Order", "order-v1", order=True),
                     _slot("carrier-d-quote", "pickup", "PickupD", "pickup-d-v1",
                           order=True, warehouse=True))),
        _tool("carrier-d-label", output="LabelD", output_schema="label-d-v1",
              slots=(_slot("carrier-d-label", "order", "Order", "order-v1", order=True),
                     _slot("carrier-d-label", "quote", "QuoteD", "quote-d-v1", order=True))),
        _tool("carrier-d-dispatch", effect="EXTERNAL_MUTATION",
              slots=(_slot("carrier-d-dispatch", "reservation", "Reservation",
                           "reservation-v1", status="HELD", order=True, warehouse=True),
                     _slot("carrier-d-dispatch", "pickup", "PickupD", "pickup-d-v1",
                           order=True, warehouse=True),
                     _slot("carrier-d-dispatch", "quote", "QuoteD", "quote-d-v1", order=True),
                     _slot("carrier-d-dispatch", "label", "LabelD", "label-d-v1", order=True))),
    )
    unique_nodes(scenario.goal, scenario.artifacts, tools)
    return Scenario("carrier-d", scenario.seed, scenario.now_ms, scenario.goal,
                    scenario.artifacts, tools, scenario.run_id)
