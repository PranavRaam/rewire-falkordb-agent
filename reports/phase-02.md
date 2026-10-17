# Rewire Phase 2 — provider-world simulator

**Status: Phase 2 core deliverable and its stated gate passed.** The simulator is an independent local service with a transactional SQLite world ledger. It is not yet connected to a coordinator, FalkorDB graph projection, MCP agent, frontend, or execution/reconciliation state machine; those belong to later phases.

## What is implemented

`services/simulator/rewire_simulator/` runs an HTTP service in a separate process and keeps provider truth in SQLite, outside FalkorDB. It seeds only public synthetic records: order O-104, warehouse W7, and held reservation R81. The carrier simulator supports Carrier B and D pickup, quote, label, booking, and operation-status lookup.

The ledger uses SQLite `BEGIN IMMEDIATE` transactions and a unique `(provider_id, operation_key)` constraint. Each successful operation record and its response are committed in the same transaction as its provider record. A key replay with the same operation and canonical payload returns the originally stored response. Reusing that key with a different operation or payload returns `IDEMPOTENCY_KEY_CONFLICT` (HTTP 409). The booking transaction also marks R81 allocated, after validating order, warehouse, reservation lifetime and quantity, quote, label, budget, and cutoff.

The simulator's clock is frozen at the time supplied at process startup (`--now-ms`), or at the current UTC millisecond if omitted. This gives the demo a deterministic clock that can be advanced explicitly by starting against the same DB with a later time. `--fault-after-commit booking` arms a one-shot fault: it commits the booking, then closes the HTTP connection before sending a response.

The provider service exposes only targeted provider APIs. It has no evaluator audit route. The evaluator reads the local SQLite database directly after the server stops; the agent-facing HTTP process does not expose the ledger or its global booking count. The SQLite path is local and ignored by Git.

## API surface

| Route | Purpose |
| --- | --- |
| `GET /health` | Liveness |
| `GET /v1/time` | Controlled synthetic clock |
| `GET /v1/inventory/orders/{orderId}` | Synthetic provider order record |
| `GET /v1/inventory/reservations/{reservationId}` | Current reservation state and expiry |
| `POST /v1/carriers/{carrier}/pickup` | Create pickup; requires `Idempotency-Key` |
| `POST /v1/carriers/{carrier}/quote` | Create quote for an existing pickup |
| `POST /v1/carriers/{carrier}/label` | Create label for a matching order/quote |
| `POST /v1/carriers/{carrier}/booking` | Create a booking and allocate reservation |
| `GET /v1/carriers/{carrier}/operations/{key}` | Look up the original provider result by key |

All mutating routes require the same caller-supplied stable idempotency-key contract. Only loopback bind addresses are accepted. The API limits JSON request size and does not log paths, keys, or payloads. There is no arbitrary Cypher, filesystem, model, or audit endpoint.

## Verification run

Run `python scripts/verify_phase2.py`. The verifier launches a fresh simulator process on loopback with a temporary SQLite file, creates pickup/quote/label, triggers a lost booking response after commit, and then exercises status recovery and replay. It shuts down the process before opening the database from evaluator code.

The saved [verification JSON](phase-02/verification.json) records **PASS** for:

- Separate provider HTTP process.
- Response loss after the booking transaction commits.
- Operation-status lookup returning the committed booking.
- Same-key replay returning the exact original booking result.
- Same key with a changed payload being rejected.
- Evaluator audit route being unavailable over HTTP.
- Evaluator-only SQLite audit finding exactly one booking and four operations (pickup, quote, label, booking).

The booking record ID is recorded in the JSON evidence. The temporary database is removed after verification; the JSON evidence contains no credentials or private data.

## Commands

From `track 01` in PowerShell:

~~~powershell
.\run-simulator.ps1 --port 8765
~~~

For a one-shot after-commit response-loss demonstration, start a fresh DB path with:

~~~powershell
.\run-simulator.ps1 --db .\data\phase2-demo-01.sqlite3 --fault-after-commit booking
~~~

Do not reuse that demo database as a fresh seeded run after booking has allocated R81. Choose a new explicit SQLite filename for a new demonstration; the service never deletes or resets a world automatically.

## Phase boundary and limitations

The simulator makes provider truth durable and independently inspectable by the evaluator. It does not make the graph a source of provider truth, and it does not implement Rewire's intent/attempt/receipt protocol. It uses a single SQLite process and synthetic carrier contracts; it does not claim production provider guarantees. Phase 3 must join graph validation, a durable logical-effect claim, stable operation keys, provider calls and reconciliation under the coordinator rules. It must treat a lost response as UNKNOWN until status evidence is checked, and must not permit a replacement carrier action just because the graph lacks a receipt.
