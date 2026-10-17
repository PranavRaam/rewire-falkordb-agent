"""End-to-end Phase 2 gate: run a separate simulator process over HTTP."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIMULATOR_PATH = ROOT / "services" / "simulator"


def request(base: str, path: str, method: str = "GET", payload=None, key=None,
            timeout: float = 2.0):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if key is not None:
        headers["Idempotency-Key"] = key
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def main() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="rewire-phase2-") as temp_dir:
        database = Path(temp_dir) / "provider-world.sqlite3"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SIMULATOR_PATH)
        command = [sys.executable, "-m", "rewire_simulator", "--host", "127.0.0.1",
                   "--port", str(port), "--db", str(database), "--now-ms", "1792230600000",
                   "--fault-after-commit", "booking"]
        process = subprocess.Popen(command, cwd=ROOT, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"simulator exited before becoming ready: {process.returncode}")
                try:
                    status, _, _ = request(base, "/health", timeout=0.5)
                    if status == 200:
                        break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("simulator did not become ready within 10 seconds")
                    time.sleep(0.1)

            _, _, order_raw = request(base, "/v1/inventory/orders/O-104")
            order = json.loads(order_raw)
            _, _, reservation_raw = request(base, "/v1/inventory/reservations/R81")
            reservation = json.loads(reservation_raw)
            base_payload = {"orderId": order["orderId"], "warehouseId": order["warehouseId"]}

            _, _, pickup_raw = request(base, "/v1/carriers/carrier-b/pickup", "POST",
                                       base_payload, "phase2:pickup:O-104")
            pickup = json.loads(pickup_raw)
            quote_payload = {**base_payload, "pickupId": pickup["pickupId"]}
            _, _, quote_raw = request(base, "/v1/carriers/carrier-b/quote", "POST",
                                       quote_payload, "phase2:quote:O-104")
            quote = json.loads(quote_raw)
            label_payload = {**quote_payload, "quoteId": quote["quoteId"]}
            _, _, label_raw = request(base, "/v1/carriers/carrier-b/label", "POST",
                                       label_payload, "phase2:label:O-104")
            label = json.loads(label_raw)

            booking_payload = {
                **base_payload,
                "reservationId": reservation["reservationId"],
                "pickupId": pickup["pickupId"],
                "quoteId": quote["quoteId"],
                "labelId": label["labelId"],
            }
            booking_key = "phase2:booking:O-104"
            response_lost = False
            try:
                request(base, "/v1/carriers/carrier-b/booking", "POST",
                        booking_payload, booking_key)
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                response_lost = True
            if not response_lost:
                raise AssertionError("fault injection should lose the first booking response")

            status, _, status_raw = request(
                base, f"/v1/carriers/carrier-b/operations/{booking_key}")
            status_doc = json.loads(status_raw)
            if status != 200 or status_doc["status"] != "CONFIRMED":
                raise AssertionError("provider status lookup did not recover the committed booking")

            replay_status, replay_headers, replay_raw = request(
                base, "/v1/carriers/carrier-b/booking", "POST", booking_payload, booking_key)
            original_result = status_doc["result"]
            if replay_status != 200 or json.loads(replay_raw) != original_result:
                raise AssertionError("same-key replay did not return the original booking result")
            if replay_headers.get("Idempotency-Replayed") != "true":
                raise AssertionError("replay response did not identify an idempotency hit")

            conflict_status, _, conflict_raw = request(
                base, "/v1/carriers/carrier-b/booking", "POST",
                {**booking_payload, "warehouseId": "W9"}, booking_key)
            if conflict_status != 409 or json.loads(conflict_raw)["error"]["code"] != "IDEMPOTENCY_KEY_CONFLICT":
                raise AssertionError("same key with a different payload was not rejected")

            audit_status, _, audit_raw = request(base, "/evaluator/audit")
            if audit_status != 404:
                raise AssertionError(f"evaluator audit must be unavailable over HTTP: {audit_raw!r}")

            checks = {
                "separateHttpProcess": True,
                "afterCommitResponseLoss": True,
                "statusLookupFindsBooking": True,
                "idempotentReplaySameResult": True,
                "sameKeyDifferentPayloadRejected": True,
                "evaluatorAuditNotExposedOverHttp": True,
            }
            verification = {
                "status": "PASS",
                "checks": checks,
                "booking": original_result,
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        # This script is the evaluator, not an HTTP-facing agent. Inspect provider truth
        # only after the service has stopped, then assert one durable booking exists.
        sys.path.insert(0, str(SIMULATOR_PATH))
        from rewire_simulator.store import FaultController, ProviderWorld  # noqa: E402

        audit = ProviderWorld(database, 1792230600000, FaultController()).evaluator_audit()
        if audit["rowCounts"]["bookings"] != 1:
            raise AssertionError(f"expected exactly one provider booking, got {audit}")
        if audit["rowCounts"]["operations"] != 4:
            raise AssertionError(f"expected pickup, quote, label, and booking operations, got {audit}")
        verification["evaluatorWorldAudit"] = audit
        verification["createdAtUtc"] = datetime.now(timezone.utc).isoformat()
        report_path = ROOT / "reports" / "phase-02" / "verification.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(verification, indent=2, sort_keys=True), encoding="utf-8")
        verification["reportPath"] = str(report_path)
        print(json.dumps(verification, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
