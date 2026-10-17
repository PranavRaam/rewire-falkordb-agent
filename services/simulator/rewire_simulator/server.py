"""Loopback-only HTTP boundary for the isolated provider simulator."""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

from rewire_simulator.store import ProviderError, ProviderWorld

MAX_BODY_BYTES = 64 * 1024
KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class SimulatorHandler(BaseHTTPRequestHandler):
    server_version = "RewireProviderSimulator/0.1"
    sys_version = ""

    @property
    def world(self) -> ProviderWorld:
        return self.server.world  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        # Avoid writing operation keys, request paths, or payloads into console logs.
        return

    def _send(self, status: int, value: dict[str, Any], *, replayed: bool = False) -> None:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if replayed:
            self.send_header("Idempotency-Replayed", "true")
        self.end_headers()
        self.wfile.write(raw)

    def _error(self, error: ProviderError) -> None:
        self._send(error.status, {"error": {"code": error.code, "message": str(error)}})

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ProviderError("INVALID_CONTENT_LENGTH", "Content-Length must be an integer", 400) from exc
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ProviderError("INVALID_BODY_SIZE", "Request body must be between 1 and 65536 bytes", 413)
        try:
            parsed = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("INVALID_JSON", "Request body must be valid JSON", 400) from exc
        if not isinstance(parsed, dict):
            raise ProviderError("INVALID_JSON_SHAPE", "Request body must be a JSON object", 400)
        return parsed

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlsplit(self.path).path
        try:
            if path == "/health":
                self._send(200, {"status": "ok", "service": "synthetic-provider-world"})
                return
            if path == "/v1/time":
                self._send(200, {"nowMs": self.world.now_ms, "clockMode": "controlled-frozen"})
                return
            parts = [unquote(part) for part in path.strip("/").split("/")]
            if len(parts) == 4 and parts[:2] == ["v1", "inventory"]:
                if parts[2] == "orders":
                    self._send(200, self.world.order(parts[3]))
                    return
                if parts[2] == "reservations":
                    self._send(200, self.world.reservation(parts[3]))
                    return
            if (len(parts) == 5 and parts[:2] == ["v1", "carriers"]
                    and parts[3] == "operations"):
                provider_id, operation_key = parts[2], parts[4]
                if not KEY_PATTERN.fullmatch(operation_key):
                    raise ProviderError("INVALID_OPERATION_KEY", "Operation key has unsupported characters", 400)
                self._send(200, self.world.operation_status(provider_id, operation_key))
                return
            raise ProviderError("ROUTE_NOT_FOUND", "No such simulator route", 404)
        except ProviderError as error:
            self._error(error)
        except Exception:
            self._send(500, {"error": {"code": "INTERNAL_PROVIDER_ERROR",
                                       "message": "The synthetic provider could not complete the request"}})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlsplit(self.path).path
        try:
            parts = [unquote(part) for part in path.strip("/").split("/")]
            if len(parts) != 4 or parts[:2] != ["v1", "carriers"]:
                raise ProviderError("ROUTE_NOT_FOUND", "No such simulator route", 404)
            provider_id, operation_type = parts[2], parts[3]
            operation_key = self.headers.get("Idempotency-Key", "")
            if not KEY_PATTERN.fullmatch(operation_key):
                raise ProviderError("INVALID_OPERATION_KEY", "A valid Idempotency-Key header is required", 400)
            payload = self._read_json()
            result, replayed, lose_response = self.world.perform(
                provider_id, operation_type, operation_key, payload)
            if lose_response:
                # The transaction is committed. Closing without an HTTP status deliberately
                # simulates transport loss after provider success.
                self.close_connection = True
                self.connection.shutdown(1)
                self.connection.close()
                return
            self._send(200, result, replayed=replayed)
        except ProviderError as error:
            self._error(error)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self._send(500, {"error": {"code": "INTERNAL_PROVIDER_ERROR",
                                       "message": "The synthetic provider could not complete the request"}})


class SimulatorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, world: ProviderWorld):
        super().__init__(address, SimulatorHandler)
        self.world = world
        self.logger = lambda message: print(f"[simulator] {message}", flush=True)


def serve(host: str, port: int, world: ProviderWorld) -> None:
    server = SimulatorHTTPServer((host, port), world)
    print(f"Synthetic provider simulator listening on http://{host}:{port}", flush=True)
    print("Provider ledger is local SQLite; no audit route is exposed.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
