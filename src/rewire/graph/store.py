"""Small official-client adapter. Query results always come from FalkorDB."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from time import perf_counter
from pathlib import Path
from typing import Any

from falkordb import FalkorDB

from rewire.domain import Goal, Tool, node_rows, relationship_rows, unique_nodes
from rewire.fixtures import Scenario

QUERY_DIR = Path(__file__).with_name("queries")
ALLOWED_RELATIONSHIPS = {
    "HAS_GOAL", "NEEDS_TYPE", "HAS_ARTIFACT", "INSTANCE_OF", "PRODUCES",
    "REQUIRES", "OF_TYPE", "CONSUMES",
}
INDEX_LABELS = (
    "Run", "Goal", "ToolRevision", "RequirementSlot", "ArtifactType", "Artifact",
    "Constraint", "Plan", "PlanStep", "Decision", "Effect", "Intent",
    "Attempt", "Receipt", "Event",
)
CONSTRAINT_LABELS = (
    "Run", "Goal", "ToolRevision", "RequirementSlot", "ArtifactType", "Artifact",
    "Constraint", "Plan", "PlanStep", "Decision", "Effect", "Intent",
    "Attempt", "Receipt", "Event",
)
QUERY_SOURCES = {
    "Q00_procedures": ["https://docs.falkordb.com/cypher/procedures"],
    "Q00_indexes": ["https://docs.falkordb.com/cypher/indexing/range-index"],
    "Q00_constraints": ["https://docs.falkordb.com/commands/graph.constraint-create"],
    "Q01_producers": ["https://docs.falkordb.com/cypher/match",
                       "https://docs.falkordb.com/cypher/optional-match",
                       "https://docs.falkordb.com/commands/graph.query"],
    "Q01R_producer_facts": ["https://docs.falkordb.com/cypher/match",
                            "https://docs.falkordb.com/commands/graph.query"],
    "Q02_bindings": ["https://docs.falkordb.com/cypher/match",
                     "https://docs.falkordb.com/cypher/optional-match",
                     "https://docs.falkordb.com/commands/graph.query"],
    "Q02R_artifact_candidates": ["https://docs.falkordb.com/cypher/match",
                                 "https://docs.falkordb.com/commands/graph.query"],
    "Q03_exact_binding": ["https://docs.falkordb.com/cypher/match",
                          "https://docs.falkordb.com/commands/graph.query"],
    "Q04_affected_steps": ["https://docs.falkordb.com/cypher/match",
                           "https://docs.falkordb.com/commands/graph.query"],
}


def load_query(query_id: str) -> str:
    exact = QUERY_DIR / f"{query_id}.cypher"
    matches = (exact,) if exact.is_file() else tuple(QUERY_DIR.glob(f"{query_id}_*.cypher"))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one file for query {query_id}, found {len(matches)}")
    return matches[0].read_text(encoding="utf-8").strip()


def result_rows(result: Any) -> list[dict[str, Any]]:
    columns = [
        str(column[-1]) if isinstance(column, (list, tuple)) else str(column)
        for column in (result.header or [])
    ]
    return [dict(zip(columns, row)) for row in result.result_set]


class GraphStore:
    def __init__(self) -> None:
        kwargs: dict[str, Any] = {
            "host": os.getenv("REWIRE_FALKOR_HOST", "127.0.0.1"),
            "port": int(os.getenv("REWIRE_FALKOR_PORT", "6379")),
        }
        username = os.getenv("REWIRE_FALKOR_USERNAME", "").strip()
        password = os.getenv("REWIRE_FALKOR_PASSWORD", "").strip()
        if username:
            kwargs["username"] = username
        if password:
            kwargs["password"] = password
        self.client = FalkorDB(**kwargs)

    def select(self, graph_name: str):
        if not graph_name.startswith("rewire_phase1_"):
            raise ValueError("Phase 1 may access only rewire_phase1_ graphs")
        return self.client.select_graph(graph_name)

    def install_schema(self, graph_name: str) -> dict[str, Any]:
        graph = self.select(graph_name)
        index_commands = []
        for label in INDEX_LABELS:
            query = f"CREATE INDEX FOR (n:{label}) ON (n.id)"
            result = graph.query(query)
            index_commands.append({
                "label": label,
                "query": query,
                "acknowledgement": "EXECUTED",
                "statistics": getattr(result, "statistics", None),
            })

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            found = self.indexes(graph_name)
            ready = {
                (row.get("label"), tuple(row.get("properties") or []))
                for row in found
                if str(row.get("status", "")).upper() in ("OPERATIONAL", "READY")
            }
            if all((label, ("id",)) in ready for label in INDEX_LABELS):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("FalkorDB indexes did not become operational within 30 seconds")

        constraint_commands = []
        for label in CONSTRAINT_LABELS:
            for kind in ("UNIQUE", "MANDATORY"):
                method = (
                    graph.create_node_unique_constraint
                    if kind == "UNIQUE" else graph.create_node_mandatory_constraint
                )
                result = method(label, "id")
                constraint_commands.append({
                    "label": label, "kind": kind,
                    # FalkorDB's client returns PENDING while the constraint builds.
                    # Operational status is recorded separately below.
                    "acknowledgement": str(result),
                })
        deadline = time.monotonic() + 30
        required = {
            (kind, label, ("id",))
            for label in CONSTRAINT_LABELS for kind in ("UNIQUE", "MANDATORY")
        }
        while time.monotonic() < deadline:
            statuses = self.constraints(graph_name)
            operational = {
                (str(row.get("type", "")).upper(), row.get("label"),
                 tuple(row.get("properties") or []))
                for row in statuses
                if str(row.get("status", "")).upper() == "OPERATIONAL"
            }
            if required.issubset(operational):
                break
            failed = [row for row in statuses
                      if str(row.get("status", "")).upper() == "FAILED"]
            if failed:
                raise RuntimeError(f"FalkorDB constraints failed: {failed}")
            time.sleep(0.2)
        else:
            raise RuntimeError("FalkorDB constraints did not become operational within 30 seconds")
        operational_indexes = self.indexes(graph_name)
        operational_constraints = self.constraints(graph_name)
        return {
            "indexCommands": index_commands,
            "operationalIndexes": operational_indexes,
            "constraintCommands": constraint_commands,
            "operationalConstraints": operational_constraints,
        }

    def constraints(self, graph_name: str) -> list[dict[str, Any]]:
        return result_rows(self.select(graph_name).ro_query(load_query("Q00_constraints")))

    def indexes(self, graph_name: str) -> list[dict[str, Any]]:
        return result_rows(self.select(graph_name).ro_query(load_query("Q00_indexes")))

    def procedures(self, graph_name: str) -> list[dict[str, Any]]:
        return result_rows(self.select(graph_name).ro_query(load_query("Q00_procedures")))

    def seed(self, graph_name: str, scenario: Scenario) -> None:
        validate_scenario(scenario)
        graph = self.select(graph_name)
        nodes_by_label: dict[str, list[dict[str, Any]]] = {}
        for label, props in node_rows(
            scenario.goal, scenario.artifacts, scenario.tools, scenario.run_id
        ):
            nodes_by_label.setdefault(label, []).append(props)
        for label, rows in nodes_by_label.items():
            if label == "ArtifactType":
                by_id: dict[str, dict[str, Any]] = {}
                for row in rows:
                    previous = by_id.setdefault(row["id"], row)
                    if previous["schemaVersion"] != row["schemaVersion"]:
                        raise ValueError(f"Conflicting ArtifactType schema for {row['id']}")
                rows = list(by_id.values())
            graph.query(
                f"UNWIND $rows AS row CREATE (n:{label} {{id: row.id}}) "
                "SET n = row RETURN count(n) AS created",
                {"rows": rows},
            )

        rels_by_type: dict[str, list[dict[str, Any]]] = {}
        for rel_type, source_id, target_id, props in relationship_rows(
            scenario.goal, scenario.artifacts, scenario.tools, scenario.run_id
        ):
            if rel_type not in ALLOWED_RELATIONSHIPS:
                raise ValueError(f"Relationship type is not allowed: {rel_type}")
            rels_by_type.setdefault(rel_type, []).append(
                {"sourceId": source_id, "targetId": target_id, **props}
            )

        endpoints = {
            "HAS_GOAL": ("Run", "Goal"), "NEEDS_TYPE": ("Goal", "ArtifactType"),
            "HAS_ARTIFACT": ("Run", "Artifact"), "INSTANCE_OF": ("Artifact", "ArtifactType"),
            "PRODUCES": ("ToolRevision", "ArtifactType"),
            "REQUIRES": ("ToolRevision", "RequirementSlot"),
            "OF_TYPE": ("RequirementSlot", "ArtifactType"),
            "CONSUMES": ("ToolRevision", "ArtifactType"),
        }
        for rel_type, rows in rels_by_type.items():
            source_label, target_label = endpoints[rel_type]
            graph.query(
                f"""UNWIND $rows AS row
MATCH (source:{source_label} {{id: row.sourceId}})
MATCH (target:{target_label} {{id: row.targetId}})
CREATE (source)-[r:{rel_type}]->(target)
SET r += row
RETURN count(r) AS created""",
                {"rows": rows},
            )

    def run_query(self, graph_name: str, query_id: str,
                  params: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        query = load_query(query_id)
        started = perf_counter()
        result = self.select(graph_name).ro_query(query, params)
        elapsed_ms = (perf_counter() - started) * 1000
        rows = result_rows(result)
        return rows, {
            "queryId": query_id,
            "query": query,
            "sha256": hashlib.sha256(query.encode()).hexdigest(),
            "sourceUrls": QUERY_SOURCES.get(query_id, []),
            "documentationStatus": "DOCUMENTED",
            "params": params,
            "rows": rows,
            "elapsedMs": round(elapsed_ms, 3),
            "rowCount": len(rows),
        }

    def close(self) -> None:
        self.client.close()


def producer_params(goal: Goal, catalog_revision: int) -> dict[str, Any]:
    return {
        "typeId": goal.output_type,
        "catalogRevision": catalog_revision,
        "weightKg": goal.weight_kg,
    }


def artifact_query_params(run_id: str, goal: Goal, now_ms: int, tool_id: str):
    return {
        "runId": run_id,
        "toolId": tool_id,
        "nowMs": now_ms,
        "orderId": goal.order_id,
        "warehouseId": goal.warehouse_id,
    }


def validate_scenario(scenario: Scenario) -> None:
    """Reject malformed contracts before graph writes; DB constraints cover only id semantics."""
    goal = scenario.goal
    if not all(isinstance(value, str) and value for value in
               (scenario.run_id, goal.id, goal.output_type, goal.order_id,
                goal.warehouse_id, goal.destination_zone)):
        raise ValueError("run and goal identifiers/scope fields must be non-empty strings")
    if not isinstance(goal.weight_kg, (int, float)) or not math.isfinite(goal.weight_kg) or goal.weight_kg <= 0:
        raise ValueError("goal weightKg must be a finite positive number")
    if not isinstance(goal.max_cost_units, int) or goal.max_cost_units < 0:
        raise ValueError("goal maxCostUnits must be a non-negative integer")
    if not isinstance(goal.cutoff_at, int) or not isinstance(scenario.now_ms, int):
        raise ValueError("cutoffAt and nowMs must be integer UTC milliseconds")
    for artifact in scenario.artifacts:
        if not all(isinstance(value, str) and value for value in
                   (artifact.id, artifact.type_id, artifact.schema_version, artifact.status,
                    artifact.order_id, artifact.warehouse_id)):
            raise ValueError(f"artifact {artifact.id!r} has an empty required string field")
        if not isinstance(artifact.version, int) or artifact.version < 1:
            raise ValueError(f"artifact {artifact.id} version must be a positive integer")
        if not isinstance(artifact.expires_at, int) or artifact.expires_at < 0:
            raise ValueError(f"artifact {artifact.id} expiresAt must be a non-negative UTC millisecond value")
        if not isinstance(artifact.properties, dict):
            raise ValueError(f"artifact {artifact.id} properties must be a mapping")
    for tool in scenario.tools:
        if not all(isinstance(value, str) and value for value in
                   (tool.id, tool.tool_id, tool.adapter_id, tool.effect_class,
                    tool.output_type, tool.output_schema_version)):
            raise ValueError(f"tool {tool.id!r} has an empty required string field")
        if not isinstance(tool.version, int) or tool.version < 1:
            raise ValueError(f"tool {tool.id} version must be a positive integer")
        if not math.isfinite(tool.max_weight_kg) or tool.max_weight_kg < 0:
            raise ValueError(f"tool {tool.id} maxWeightKg must be finite and non-negative")
        for slot in tool.slots:
            if slot.cardinality != 1:
                raise ValueError(f"Phase 1 supports exactly-one slots; {slot.id} has cardinality {slot.cardinality}")
            if not all(isinstance(value, str) and value for value in
                       (slot.id, slot.name, slot.type_id, slot.schema_version,
                        slot.required_status, slot.rule_id)):
                raise ValueError(f"slot {slot.id!r} has an empty required string field")
            if not isinstance(slot.min_version, int) or slot.min_version < 1:
                raise ValueError(f"slot {slot.id} minVersion must be a positive integer")
            if not isinstance(slot.scope_order, bool) or not isinstance(slot.scope_warehouse, bool):
                raise ValueError(f"slot {slot.id} scope flags must be boolean")
    # Detect duplicate IDs and conflicting ArtifactType schema declarations before writes.
    unique_nodes(goal, scenario.artifacts, scenario.tools, scenario.run_id)
