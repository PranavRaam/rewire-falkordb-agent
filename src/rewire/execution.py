"""Single-process coordinator for durable external-effect intents.

This module deliberately supports the synthetic carrier adapter used by the
hackathon fixture. It does not claim exactly-once behavior for arbitrary APIs.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from typing import Any

from rewire.graph.store import GraphStore, result_rows, load_query


def canonical_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ExecutionCoordinator:
    """Serialize graph state transitions; never hold the lock over HTTP."""

    def __init__(self, store: GraphStore, graph_name: str, run_id: str):
        self.store, self.graph_name, self.run_id = store, graph_name, run_id
        self.graph = store.select(graph_name)
        self._lock = threading.RLock()

    def read(self, query_id: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return result_rows(self.graph.ro_query(load_query(query_id), params))

    def transition(self, query_id: str, params: dict[str, Any], *, required: bool = True):
        """Execute a revision-guarded mutation within the coordinator lock."""
        with self._lock:
            rows = result_rows(self.graph.query(load_query(query_id), params))
            if not required and not rows:
                return []
            if len(rows) != 1:
                raise RuntimeError(f"{query_id} denied or ambiguous: {rows}")
            return rows[0]

    def project_booking(self, params: dict[str, Any]) -> dict[str, Any]:
        """Idempotent graph projection: a committed projection is read back on retry."""
        with self._lock:
            rows = result_rows(self.graph.ro_query(load_query("Q14_read_booking_projection"), params))
            if rows:
                row = rows[0]
                expected = {"artifactId": params["artifactId"], "typeId": params["typeId"],
                    "schemaVersion": params["schemaVersion"], "orderId": params["orderId"],
                    "warehouseId": params["warehouseId"], "bookingId": params["providerRecordId"],
                    "receiptStatus": "CONFIRMED", "runStatus": "SUCCEEDED"}
                if any(row.get(key) != value for key, value in expected.items()):
                    raise RuntimeError(f"existing booking projection conflicts with receipt: {row}")
                return {**row, "replayed": True}
            rows = result_rows(self.graph.query(load_query("Q12_project_booking"), params))
            if len(rows) != 1:
                raise RuntimeError(f"Q12_project_booking denied or ambiguous: {rows}")
            return {**rows[0], "replayed": False}

    def claim_intent(self, params: dict[str, Any]) -> dict[str, Any]:
        """Deduplicate caller retries by operation key and payload identity."""
        with self._lock:
            existing = result_rows(self.graph.ro_query(
                load_query("Q08C_lookup_operation"), params))
            if existing:
                row = existing[0]
                expected = {"effectId": params["effectId"], "operationKey": params["operationKey"],
                    "payloadHash": params["payloadHash"], "providerId": params["providerId"],
                    "stepId": params["stepId"]}
                if any(row.get(key) != value for key, value in expected.items()):
                    raise RuntimeError(f"operation-key replay conflicts with persisted intent: {row}")
                return {**row, "replayed": True}
            rows = result_rows(self.graph.query(load_query("Q08_claim_intent"), params))
            if len(rows) != 1:
                raise RuntimeError(f"Q08_claim_intent denied or ambiguous: {rows}")
            return {**rows[0], "replayed": False}

    @staticmethod
    def ids(prefix: str) -> dict[str, str]:
        return {name: f"{prefix}:{uuid.uuid4().hex}" for name in
                ("intentId", "attemptId", "receiptId", "eventId")}

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)

