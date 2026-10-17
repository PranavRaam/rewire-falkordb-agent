"""Start the Rewire provider simulator as an independent process."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from rewire_simulator.server import serve
from rewire_simulator.store import FaultController, ProviderWorld


def main() -> None:
    parser = argparse.ArgumentParser(prog="rewire-simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=os.getenv(
        "REWIRE_SIMULATOR_DB", str(Path(__file__).resolve().parents[3] / "data" / "provider-world.sqlite3")))
    parser.add_argument("--now-ms", type=int, default=None,
                        help="freeze the synthetic provider clock at a chosen UTC millisecond")
    parser.add_argument("--fault-after-commit", choices=("booking",), default=None,
                        help="lose the response after the next successful booking commit")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        parser.error("the Phase 2 simulator binds to loopback only")
    now_ms = (args.now_ms if args.now_ms is not None
              else int(datetime.now(timezone.utc).timestamp() * 1000))
    faults = FaultController(after_commit_operation=args.fault_after_commit,
                             remaining=1 if args.fault_after_commit else 0)
    world = ProviderWorld(args.db, now_ms, faults)
    serve(args.host, args.port, world)


if __name__ == "__main__":
    main()
