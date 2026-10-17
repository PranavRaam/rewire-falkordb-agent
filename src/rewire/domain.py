"""Typed, database-independent Phase 1 domain contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Goal:
    id: str
    output_type: str
    order_id: str
    warehouse_id: str
    destination_zone: str
    weight_kg: float
    max_cost_units: int
    cutoff_at: int


@dataclass(frozen=True)
class Artifact:
    id: str
    type_id: str
    schema_version: str
    version: int
    status: str
    expires_at: int
    order_id: str
    warehouse_id: str
    properties: dict[str, Any]

    def as_node(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "typeId": self.type_id,
            "schemaVersion": self.schema_version,
            "version": self.version,
            "status": self.status,
            "expiresAt": self.expires_at,
            "orderId": self.order_id,
            "warehouseId": self.warehouse_id,
            **self.properties,
        }


@dataclass(frozen=True)
class Slot:
    id: str
    name: str
    type_id: str
    cardinality: int
    schema_version: str
    min_version: int
    required_status: str
    scope_order: bool
    scope_warehouse: bool
    rule_id: str
    output_bindings: dict[str, str]

    def as_node(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "cardinality": self.cardinality,
            "schemaVersion": self.schema_version,
            "minVersion": self.min_version,
            "requiredStatus": self.required_status,
            "scopeOrder": self.scope_order,
            "scopeWarehouse": self.scope_warehouse,
            "ruleId": self.rule_id,
            "outputBindingsJson": _canonical(self.output_bindings),
        }


@dataclass(frozen=True)
class Tool:
    id: str
    tool_id: str
    version: int
    catalog_revision: int
    enabled: bool
    adapter_id: str
    effect_class: str
    max_weight_kg: float
    output_type: str
    output_schema_version: str
    slots: tuple[Slot, ...]
    output_bindings: dict[str, str]
    consumes: tuple[str, ...] = ()

    def as_node(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "toolId": self.tool_id,
            "version": self.version,
            "catalogRevision": self.catalog_revision,
            "enabled": self.enabled,
            "adapterId": self.adapter_id,
            "effectClass": self.effect_class,
            "maxWeightKg": self.max_weight_kg,
            "outputBindingsJson": _canonical(self.output_bindings),
        }


def _canonical(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def node_rows(goal: Goal, artifacts: tuple[Artifact, ...], tools: tuple[Tool, ...], run_id: str):
    """Yield static-label node rows; labels never come from dataset input."""
    yield "Run", {
        "id": run_id,
        "stateRevision": 1,
        "catalogRevision": 1,
        "selectedPlanId": "",
        "status": "READY",
    }
    yield "Goal", {
        "id": goal.id,
        "orderId": goal.order_id,
        "warehouseId": goal.warehouse_id,
        "destinationZone": goal.destination_zone,
        "weightKg": goal.weight_kg,
        "maxCostUnits": goal.max_cost_units,
        "cutoffAt": goal.cutoff_at,
        "outputTypeId": goal.output_type,
    }
    yield "ArtifactType", {"id": goal.output_type, "schemaVersion": "booking-v1"}
    for tool in tools:
        yield "ArtifactType", {"id": tool.output_type, "schemaVersion": tool.output_schema_version}
        for slot in tool.slots:
            yield "ArtifactType", {"id": slot.type_id, "schemaVersion": slot.schema_version}
    for artifact in artifacts:
        yield "ArtifactType", {"id": artifact.type_id, "schemaVersion": artifact.schema_version}
        yield "Artifact", artifact.as_node()
    for tool in tools:
        yield "ToolRevision", tool.as_node()
        for slot in tool.slots:
            yield "RequirementSlot", slot.as_node()


def relationship_rows(goal: Goal, artifacts: tuple[Artifact, ...], tools: tuple[Tool, ...], run_id: str):
    """Produce relationship rows with a fixed allow-listed type set."""
    yield "HAS_GOAL", run_id, goal.id, {}
    yield "NEEDS_TYPE", goal.id, goal.output_type, {}
    for artifact in artifacts:
        yield "HAS_ARTIFACT", run_id, artifact.id, {}
        yield "INSTANCE_OF", artifact.id, artifact.type_id, {}
    for tool in tools:
        yield "PRODUCES", tool.id, tool.output_type, {}
        for slot in tool.slots:
            yield "REQUIRES", tool.id, slot.id, {}
            yield "OF_TYPE", slot.id, slot.type_id, {}
        for type_id in tool.consumes:
            yield "CONSUMES", tool.id, type_id, {}


def unique_nodes(goal: Goal, artifacts: tuple[Artifact, ...], tools: tuple[Tool, ...],
                 run_id: str = "run-phase1-fixture"):
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for label, props in node_rows(goal, artifacts, tools, run_id):
        key = (label, str(props["id"]))
        if key in seen:
            if label == "ArtifactType" and seen[key] == props:
                continue
            raise ValueError(f"duplicate/conflicting {label} id: {props['id']}")
        seen[key] = props


def model_dump(value: Any) -> dict[str, Any]:
    return asdict(value)
