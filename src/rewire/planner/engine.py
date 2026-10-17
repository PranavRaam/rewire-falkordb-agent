"""Phase 1 conditional planner. It never executes provider actions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from rewire.domain import Goal
from rewire.graph.store import GraphStore, producer_params

MAX_DEPTH = 12
MAX_EXPANSIONS = 2000


@dataclass
class PlanContext:
    steps: list[dict[str, Any]] = field(default_factory=list)
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    consumed: set[str] = field(default_factory=set)
    reused: set[str] = field(default_factory=set)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def clone(self) -> "PlanContext":
        return PlanContext(
            steps=[dict(step, inputs=[dict(x) for x in step["inputs"]]) for step in self.steps],
            outputs={key: dict(value) for key, value in self.outputs.items()},
            consumed=set(self.consumed),
            reused=set(self.reused),
            rejected=list(self.rejected),
        )


class ConditionalPlanner:
    def __init__(self, store: GraphStore, graph_name: str, run_id: str,
                 goal: Goal, now_ms: int, catalog_revision: int,
                 max_depth: int = MAX_DEPTH):
        self.store = store
        self.graph_name = graph_name
        self.run_id = run_id
        self.goal = goal
        self.now_ms = now_ms
        self.catalog_revision = catalog_revision
        rows = store.select(graph_name).ro_query(
            "MATCH (r:Run {id:$id}) RETURN r.stateRevision", {"id": run_id}).result_set
        if len(rows) != 1:
            raise ValueError("run not found")
        self.revision = rows[0][0]
        self.max_depth = max_depth
        self.expansions = 0
        self.truncated = False
        self.query_evidence: list[dict[str, Any]] = []
        self.global_rejections: list[dict[str, Any]] = []
        self.blockers: list[dict[str, Any]] = []
        self._producer_cache: dict[str, list[dict[str, Any]]] = {}
        self._binding_cache: dict[tuple[str, str], tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}

    def _query(self, query_id: str, params: dict[str, Any]):
        rows, evidence = self.store.run_query(self.graph_name, query_id, params)
        self.query_evidence.append(evidence)
        return rows

    def _producer_rows(self, output_type: str) -> list[dict[str, Any]]:
        if output_type in self._producer_cache:
            return self._producer_cache[output_type]
        params = {
            "typeId": output_type,
            "catalogRevision": self.catalog_revision,
            "weightKg": self.goal.weight_kg,
        }
        rows = self._query("Q01_producers", params)
        facts = self._query("Q01R_producer_facts", {
            "typeId": output_type,
            "catalogRevision": self.catalog_revision,
        })
        accepted_tools = {row["toolId"] for row in rows}
        for fact in facts:
            if fact["toolId"] in accepted_tools:
                continue
            reason = "TOOL_DISABLED" if not fact["enabled"] else (
                "PACKAGE_WEIGHT_EXCEEDS_TOOL_LIMIT"
                if fact["maxWeightKg"] not in (0, 0.0)
                and fact["maxWeightKg"] < self.goal.weight_kg
                else "PRODUCER_NOT_ELIGIBLE"
            )
            self.global_rejections.append({
                "toolId": fact["toolId"],
                "reasonCode": reason,
                "observed": {
                    "enabled": fact["enabled"],
                    "maxWeightKg": fact["maxWeightKg"],
                    "requestedWeightKg": self.goal.weight_kg,
                },
                "evidenceQueryId": "Q01R_producer_facts",
            })
        self._producer_cache[output_type] = rows
        return rows

    @staticmethod
    def _slot_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.get("slotId") is None:
                continue
            slot_id = row["slotId"]
            groups.setdefault(slot_id, {
                "id": slot_id,
                "name": row["slotName"],
                "typeId": row["inputTypeId"],
                "cardinality": row["cardinality"],
                "schemaVersion": row["schemaVersion"],
                "minVersion": row["minVersion"],
                "requiredStatus": row["requiredStatus"],
                "scopeOrder": row["scopeOrder"],
                "scopeWarehouse": row["scopeWarehouse"],
                "ruleId": row["ruleId"],
                "outputBindings": json.loads(row["slotOutputBindingsJson"] or "{}"),
            })
        return [groups[key] for key in sorted(groups)]

    def _artifact_candidates(self, tool_id: str, slot: dict[str, Any],
                             state: PlanContext):
        key = (tool_id, slot["id"])
        if key not in self._binding_cache:
            base_params = {
                "runId": self.run_id,
                "toolId": tool_id,
                "nowMs": self.now_ms,
                "orderId": self.goal.order_id,
                "warehouseId": self.goal.warehouse_id,
            }
            filtered = self._query("Q02_bindings", base_params)
            raw = self._query("Q02R_artifact_candidates", {
                "runId": self.run_id, "typeId": slot["typeId"],
            })
            self._binding_cache[key] = (filtered, raw)
        filtered, raw = self._binding_cache[key]
        valid_ids = {
            row["artifactId"] for row in filtered
            if row["slotId"] == slot["id"] and row["artifactId"] is not None
        }
        valid = []
        for artifact in raw:
            if artifact["artifactId"] in state.consumed:
                continue
            reasons = []
            if artifact["schemaVersion"] != slot["schemaVersion"]:
                reasons.append("SCHEMA_VERSION_MISMATCH")
            if artifact["version"] < slot["minVersion"]:
                reasons.append("BELOW_MINIMUM_VERSION")
            if slot["requiredStatus"] != "*" and artifact["status"] != slot["requiredStatus"]:
                reasons.append("STATUS_MISMATCH")
            if artifact["expiresAt"] != 0 and artifact["expiresAt"] <= self.now_ms:
                reasons.append("EXPIRED")
            if slot["scopeOrder"] and artifact["orderId"] != self.goal.order_id:
                reasons.append("ORDER_SCOPE_MISMATCH")
            if slot["scopeWarehouse"] and artifact["warehouseId"] != self.goal.warehouse_id:
                reasons.append("WAREHOUSE_SCOPE_MISMATCH")
            if artifact["artifactId"] not in valid_ids and not reasons:
                reasons.append("NOT_ACCEPTED_BY_GRAPH_BINDING_QUERY")
            if reasons:
                state.rejected.append({
                    "artifactId": artifact["artifactId"],
                    "slotId": slot["id"],
                    "reasonCodes": reasons,
                    "evidenceQueryIds": ["Q02_bindings", "Q02R_artifact_candidates"],
                })
            else:
                valid.append(artifact)
        valid.sort(key=lambda row: row["artifactId"])
        return valid

    def _step_id(self, state: PlanContext, tool_id: str) -> str:
        return f"step:{len(state.steps) + 1}:{tool_id}"

    def _expand_type(self, output_type: str, depth: int, stack: tuple[str, ...],
                     state: PlanContext) -> list[PlanContext]:
        if output_type in state.outputs:
            return [state]
        if output_type in stack:
            state.rejected.append({
                "typeId": output_type, "reasonCodes": ["DEPENDENCY_CYCLE"],
            })
            self.blockers.append({
                "typeId": output_type, "reasonCode": "DEPENDENCY_CYCLE",
            })
            return []
        if depth > self.max_depth:
            self.truncated = True
            return []
        self.expansions += 1
        if self.expansions > MAX_EXPANSIONS:
            self.truncated = True
            return []

        producer_rows = self._producer_rows(output_type)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in producer_rows:
            grouped.setdefault(row["toolId"], []).append(row)
        if not grouped:
            self.blockers.append({
                "typeId": output_type, "reasonCode": "NO_ELIGIBLE_PRODUCER",
            })
            return []

        completed: list[PlanContext] = []
        for tool_id in sorted(grouped):
            rows = grouped[tool_id]
            tool = rows[0]
            slots = self._slot_groups(rows)
            if any(slot["cardinality"] != 1 for slot in slots):
                state.rejected.append({
                    "toolId": tool_id,
                    "reasonCodes": ["UNSUPPORTED_SLOT_CARDINALITY"],
                })
                continue
            branches: list[tuple[PlanContext, list[dict[str, Any]]]] = [(state.clone(), [])]
            for slot in slots:
                next_branches: list[tuple[PlanContext, list[dict[str, Any]]]] = []
                for branch, inputs in branches:
                    observed = self._artifact_candidates(tool_id, slot, branch)
                    choices: list[tuple[PlanContext, dict[str, Any]]] = []
                    for artifact in observed:
                        # Recheck exact version/status/expiry in Q03 before using a binding.
                        exact_params = {
                            "runId": self.run_id,
                            "artifactId": artifact["artifactId"],
                            "typeId": slot["typeId"],
                            "expectedRevision": self.revision,
                            "expectedArtifactVersion": artifact["version"],
                            "schemaVersion": slot["schemaVersion"],
                            "requiredStatus": artifact["status"],
                            "nowMs": self.now_ms,
                            "orderId": self.goal.order_id,
                            "warehouseId": self.goal.warehouse_id,
                        }
                        exact = self._query("Q03_exact_binding", exact_params)
                        if not exact:
                            branch.rejected.append({
                                "artifactId": artifact["artifactId"],
                                "slotId": slot["id"],
                                "reasonCodes": ["Q03_REJECTED_Q02_BINDING"],
                            })
                            continue
                        chosen = branch.clone()
                        chosen.reused.add(artifact["artifactId"])
                        choices.append((chosen, {
                            "slotId": slot["id"], "typeId": slot["typeId"],
                            "artifactId": artifact["artifactId"],
                            "artifactVersion": artifact["version"],
                        }))
                    symbolic = branch.outputs.get(slot["typeId"])
                    if symbolic is not None:
                        choices.append((branch.clone(), {
                            "slotId": slot["id"], "typeId": slot["typeId"],
                            "producerStepId": symbolic["stepId"],
                            "producerPort": "output",
                        }))
                    if not choices:
                        child_branches = self._expand_type(
                            slot["typeId"], depth + 1, stack + (output_type,), branch.clone()
                        )
                        for child in child_branches:
                            symbolic = child.outputs.get(slot["typeId"])
                            if symbolic is not None:
                                choices.append((child, {
                                    "slotId": slot["id"], "typeId": slot["typeId"],
                                    "producerStepId": symbolic["stepId"],
                                    "producerPort": "output",
                                }))
                    if not choices:
                        self.blockers.append({
                            "toolId": tool_id, "slotId": slot["id"],
                            "typeId": slot["typeId"],
                            "reasonCode": "REQUIRED_SLOT_UNSATISFIED",
                        })
                    for chosen, binding in choices:
                        next_branches.append((chosen, inputs + [binding]))
                branches = next_branches
                if not branches:
                    break
            for branch, inputs in branches:
                step_id = self._step_id(branch, tool_id)
                branch.steps.append({
                    "id": step_id, "toolId": tool_id,
                    "toolVersion": tool["toolVersion"],
                    "adapterId": tool["adapterId"],
                    "effectClass": tool["effectClass"],
                    "inputs": inputs,
                    "consumesTypes": sorted({
                        row["consumedTypeId"] for row in rows
                        if row.get("consumedTypeId") is not None
                    }),
                    "status": "CONDITIONAL",
                    "expectedOutputType": output_type,
                })
                consumed = set(branch.steps[-1]["consumesTypes"])
                for binding in inputs:
                    if binding["typeId"] in consumed and "artifactId" in binding:
                        branch.consumed.add(binding["artifactId"])
                branch.outputs[output_type] = {"stepId": step_id}
                completed.append(branch)
        return completed

    def discover(self) -> dict[str, Any]:
        contexts = self._expand_type(self.goal.output_type, 0, (), PlanContext())
        contexts.sort(key=lambda item: (
            len(item.steps), tuple(step["toolId"] for step in item.steps)
        ))
        selected = contexts[0] if contexts else None
        status = (
            "STRUCTURALLY_VALID" if selected is not None else
            "SEARCH_LIMIT_REACHED" if self.truncated else "EXHAUSTIVE_NO_PLAN"
        )
        steps = []
        if selected:
            steps = [{"ordinal": i + 1, **step}
                     for i, step in enumerate(selected.steps)]
        return {
            "status": status,
            "graphName": self.graph_name,
            "runId": self.run_id,
            "goal": self.goal.__dict__,
            "planner": "bounded-python-and-or-v1",
            "limits": {"maxDepth": self.max_depth, "maxExpansions": MAX_EXPANSIONS},
            "exploredExpansions": self.expansions,
            "steps": steps,
            "preservedArtifacts": sorted(selected.reused) if selected else [],
            "conditionalChecks": [
                "provider quote price <= goal maximum cost",
                "provider response and artifact fields match bound order/warehouse/package",
                "cutoff remains satisfied at execution time",
            ] if selected else [],
            "rejected": self.global_rejections + (selected.rejected if selected else []),
            "blockers": self.blockers,
            "evidence": self.query_evidence,
        }

