"""Transactional synthetic inventory and carrier ledger.

The SQLite file is provider truth. It is intentionally not exposed by the HTTP API;
only the separate evaluator process may inspect its tables directly.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ProviderError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code = code
        self.status = status


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class FaultController:
    after_commit_operation: str | None = None
    remaining: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def consume(self, operation_type: str) -> bool:
        with self.lock:
            if self.remaining > 0 and self.after_commit_operation == operation_type:
                self.remaining -= 1
                return True
            return False


class ProviderWorld:
    """Inventory and carrier providers stored independently from FalkorDB."""

    def __init__(self, database_path: str | Path, now_ms: int,
                 faults: FaultController | None = None):
        self.database_path = str(database_path)
        self.now_ms = now_ms
        self.faults = faults or FaultController()
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("PRAGMA synchronous = FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    weight_kg REAL NOT NULL,
                    warehouse_id TEXT NOT NULL,
                    destination_zone TEXT NOT NULL,
                    max_cost_units INTEGER NOT NULL,
                    cutoff_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS warehouses (
                    warehouse_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL REFERENCES orders(order_id),
                    warehouse_id TEXT NOT NULL REFERENCES warehouses(warehouse_id),
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operations (
                    provider_id TEXT NOT NULL,
                    operation_key TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (provider_id, operation_key),
                    UNIQUE (provider_id, record_id)
                );
                CREATE TABLE IF NOT EXISTS pickups (
                    pickup_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL REFERENCES orders(order_id),
                    warehouse_id TEXT NOT NULL REFERENCES warehouses(warehouse_id),
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quotes (
                    quote_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL REFERENCES orders(order_id),
                    pickup_id TEXT NOT NULL REFERENCES pickups(pickup_id),
                    price_units INTEGER NOT NULL,
                    service_id TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS labels (
                    label_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL REFERENCES orders(order_id),
                    quote_id TEXT NOT NULL REFERENCES quotes(quote_id),
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    order_id TEXT NOT NULL REFERENCES orders(order_id),
                    reservation_id TEXT NOT NULL REFERENCES reservations(reservation_id),
                    pickup_id TEXT NOT NULL REFERENCES pickups(pickup_id),
                    quote_id TEXT NOT NULL REFERENCES quotes(quote_id),
                    label_id TEXT NOT NULL REFERENCES labels(label_id),
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
            """)
            db.execute(
                "INSERT OR IGNORE INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("O-104", "M-8 motor", 1, 8.0, "W7", "Z3", 900,
                 self.now_ms + 40 * 60 * 1000),
            )
            db.execute("INSERT OR IGNORE INTO warehouses VALUES (?, ?)", ("W7", "ACTIVE"))
            db.execute(
                "INSERT OR IGNORE INTO reservations VALUES (?, ?, ?, ?, ?, ?)",
                ("R81", "O-104", "W7", 1, "HELD", self.now_ms + 20 * 60 * 1000),
            )

    def _row(self, table: str, key_column: str, value: str) -> dict[str, Any] | None:
        # Table and key names are fixed call-site literals, never user supplied.
        with closing(self._connect()) as db:
            row = db.execute(f"SELECT * FROM {table} WHERE {key_column} = ?", (value,)).fetchone()
            return dict(row) if row else None

    def order(self, order_id: str) -> dict[str, Any]:
        row = self._row("orders", "order_id", order_id)
        if not row:
            raise ProviderError("ORDER_NOT_FOUND", "No such synthetic order", 404)
        return {"orderId": row["order_id"], "sku": row["sku"],
                "quantity": row["quantity"], "weightKg": row["weight_kg"],
                "warehouseId": row["warehouse_id"],
                "destinationZone": row["destination_zone"],
                "maxCostUnits": row["max_cost_units"], "cutoffAt": row["cutoff_at"]}

    def reservation(self, reservation_id: str) -> dict[str, Any]:
        row = self._row("reservations", "reservation_id", reservation_id)
        if not row:
            raise ProviderError("RESERVATION_NOT_FOUND", "No such reservation", 404)
        return {"reservationId": row["reservation_id"], "orderId": row["order_id"],
                "warehouseId": row["warehouse_id"], "quantity": row["quantity"],
                "status": row["status"], "expiresAt": row["expires_at"]}

    def operation_status(self, provider_id: str, operation_key: str) -> dict[str, Any]:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT operation_type, payload_hash, record_id, response_json, created_at "
                "FROM operations WHERE provider_id = ? AND operation_key = ?",
                (provider_id, operation_key),
            ).fetchone()
        if not row:
            raise ProviderError("OPERATION_NOT_FOUND", "No operation found for this key", 404)
        return {
            "providerId": provider_id,
            "operationKey": operation_key,
            "operationType": row["operation_type"],
            "status": "CONFIRMED",
            "recordId": row["record_id"],
            "createdAt": row["created_at"],
            "result": json.loads(row["response_json"]),
        }

    def perform(self, provider_id: str, operation_type: str, operation_key: str,
                payload: dict[str, Any]) -> tuple[dict[str, Any], bool, bool]:
        if provider_id not in ("carrier-b", "carrier-d"):
            raise ProviderError("PROVIDER_NOT_FOUND", "Only synthetic Carrier B and D are enabled", 404)
        if not operation_key or len(operation_key) > 128:
            raise ProviderError("INVALID_OPERATION_KEY", "Idempotency-Key must contain 1–128 characters")
        if operation_type not in ("pickup", "quote", "label", "booking"):
            raise ProviderError("OPERATION_NOT_SUPPORTED", "Unsupported operation type", 404)
        payload_hash = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT operation_type, payload_hash, response_json FROM operations "
                "WHERE provider_id = ? AND operation_key = ?",
                (provider_id, operation_key),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash or existing["operation_type"] != operation_type:
                    raise ProviderError("IDEMPOTENCY_KEY_CONFLICT",
                                        "This key was already used with a different operation or payload", 409)
                original = json.loads(existing["response_json"])
                db.commit()
                return original, True, False

            record_id, response = self._create_record(db, provider_id, operation_type, payload)
            response_json = canonical_json(response)
            db.execute(
                "INSERT INTO operations(provider_id, operation_key, operation_type, payload_hash, "
                "record_id, response_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (provider_id, operation_key, operation_type, payload_hash, record_id,
                 response_json, self.now_ms),
            )
            db.commit()
            lose_response = operation_type == "booking" and self.faults.consume("booking")
            return response, False, lose_response
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _create_record(self, db: sqlite3.Connection, provider_id: str,
                       operation_type: str, payload: dict[str, Any]):
        order_id = payload.get("orderId")
        if not isinstance(order_id, str) or not order_id:
            raise ProviderError("INVALID_ORDER_ID", "orderId must be a non-empty string", 400)
        warehouse_id = payload.get("warehouseId")
        if warehouse_id is not None and (not isinstance(warehouse_id, str) or not warehouse_id):
            raise ProviderError("INVALID_WAREHOUSE_ID", "warehouseId must be a non-empty string", 400)
        order = db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not order:
            raise ProviderError("ORDER_NOT_FOUND", "No such synthetic order", 404)
        if order["cutoff_at"] <= self.now_ms:
            raise ProviderError("ORDER_CUTOFF_PASSED", "The synthetic dispatch cutoff has passed")
        if warehouse_id is not None and warehouse_id != order["warehouse_id"]:
            raise ProviderError("WAREHOUSE_SCOPE_MISMATCH", "Warehouse does not match the order")

        if operation_type == "pickup":
            warehouse = db.execute("SELECT status FROM warehouses WHERE warehouse_id = ?",
                                   (order["warehouse_id"],)).fetchone()
            if not warehouse or warehouse["status"] != "ACTIVE":
                raise ProviderError("WAREHOUSE_UNAVAILABLE", "Warehouse is not active")
            pickup_id = f"PU-{uuid.uuid4().hex[:10].upper()}"
            db.execute("INSERT INTO pickups VALUES (?, ?, ?, ?, ?)",
                       (pickup_id, order_id, order["warehouse_id"], "READY", self.now_ms))
            return pickup_id, {"pickupId": pickup_id, "orderId": order_id,
                               "warehouseId": order["warehouse_id"], "status": "READY"}

        pickup_id = payload.get("pickupId")
        if not isinstance(pickup_id, str) or not pickup_id:
            raise ProviderError("INVALID_PICKUP_ID", "pickupId must be a non-empty string", 400)
        pickup = db.execute("SELECT * FROM pickups WHERE pickup_id = ? AND order_id = ?",
                            (pickup_id, order_id)).fetchone()
        if not pickup:
            raise ProviderError("PICKUP_NOT_FOUND", "A pickup for this order is required")
        if pickup["warehouse_id"] != order["warehouse_id"]:
            raise ProviderError("WAREHOUSE_SCOPE_MISMATCH", "Pickup belongs to another warehouse")

        if operation_type == "quote":
            quote_id = f"QT-{uuid.uuid4().hex[:10].upper()}"
            price = 300 + int(order["weight_kg"] * 52)
            expires_at = min(order["cutoff_at"], self.now_ms + 15 * 60 * 1000)
            db.execute("INSERT INTO quotes VALUES (?, ?, ?, ?, ?, ?)",
                       (quote_id, order_id, pickup_id, price, f"{provider_id}-standard", expires_at))
            return quote_id, {"quoteId": quote_id, "orderId": order_id,
                              "pickupId": pickup_id, "priceUnits": price,
                              "serviceId": f"{provider_id}-standard", "expiresAt": expires_at}

        quote_id = payload.get("quoteId")
        if not isinstance(quote_id, str) or not quote_id:
            raise ProviderError("INVALID_QUOTE_ID", "quoteId must be a non-empty string", 400)
        quote = db.execute("SELECT * FROM quotes WHERE quote_id = ? AND order_id = ?",
                           (quote_id, order_id)).fetchone()
        if not quote:
            raise ProviderError("QUOTE_NOT_FOUND", "A quote for this order is required")
        if quote["pickup_id"] != pickup_id:
            raise ProviderError("PICKUP_QUOTE_MISMATCH", "Quote was created for another pickup")
        if quote["expires_at"] <= self.now_ms:
            raise ProviderError("QUOTE_EXPIRED", "The quote has expired")
        if operation_type == "label":
            label_id = f"LB-{uuid.uuid4().hex[:10].upper()}"
            db.execute("INSERT INTO labels VALUES (?, ?, ?, ?, ?)",
                       (label_id, order_id, quote_id, "READY", self.now_ms))
            return label_id, {"labelId": label_id, "orderId": order_id,
                              "quoteId": quote_id, "status": "READY"}

        reservation_id = payload.get("reservationId")
        if not isinstance(reservation_id, str) or not reservation_id:
            raise ProviderError("INVALID_RESERVATION_ID", "reservationId must be a non-empty string", 400)
        reservation = db.execute(
            "SELECT * FROM reservations WHERE reservation_id = ? AND order_id = ?",
            (reservation_id, order_id),
        ).fetchone()
        if not reservation:
            raise ProviderError("RESERVATION_NOT_FOUND", "A reservation for this order is required")
        if reservation["warehouse_id"] != order["warehouse_id"]:
            raise ProviderError("WAREHOUSE_SCOPE_MISMATCH", "Reservation belongs to another warehouse")
        if reservation["quantity"] < order["quantity"]:
            raise ProviderError("RESERVATION_QUANTITY_INSUFFICIENT",
                                "Reservation does not cover the order quantity")
        if reservation["status"] != "HELD" or reservation["expires_at"] <= self.now_ms:
            raise ProviderError("RESERVATION_UNAVAILABLE", "Reservation is not held and unexpired")
        if quote["price_units"] > order["max_cost_units"]:
            raise ProviderError("PRICE_OVER_BUDGET", "Quote exceeds the order's maximum cost")
        label_id = payload.get("labelId")
        if not isinstance(label_id, str) or not label_id:
            raise ProviderError("INVALID_LABEL_ID", "labelId must be a non-empty string", 400)
        label = db.execute("SELECT * FROM labels WHERE label_id = ? AND order_id = ?",
                           (label_id, order_id)).fetchone()
        if not label or label["quote_id"] != quote_id:
            raise ProviderError("LABEL_QUOTE_MISMATCH", "Label must match this order and quote")
        booking_id = f"BK-{uuid.uuid4().hex[:10].upper()}"
        db.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (booking_id, provider_id, order_id, reservation_id, pickup_id,
                    quote_id, label_id, "CONFIRMED", self.now_ms))
        db.execute("UPDATE reservations SET status = 'ALLOCATED' WHERE reservation_id = ?",
                   (reservation_id,))
        return booking_id, {"bookingId": booking_id, "providerId": provider_id,
                            "orderId": order_id, "reservationId": reservation_id,
                            "pickupId": pickup_id, "quoteId": quote_id,
                            "labelId": label_id, "status": "CONFIRMED",
                            "createdAt": self.now_ms}

    def evaluator_audit(self) -> dict[str, Any]:
        """Offline evaluator-only view; deliberately not routed by the HTTP server."""
        with closing(self._connect()) as db:
            counts = {}
            for table in ("orders", "warehouses", "reservations", "operations", "pickups",
                          "quotes", "labels", "bookings"):
                counts[table] = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            bookings = [dict(row) for row in db.execute("SELECT * FROM bookings ORDER BY booking_id")]
        return {"rowCounts": counts, "bookings": bookings}
