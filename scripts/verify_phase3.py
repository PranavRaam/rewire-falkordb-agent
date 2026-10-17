"""End-to-end Phase 3 gate on an owned FalkorDB graph and local simulator."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "services" / "simulator"))
from rewire.phase1 import run_phase1  # noqa: E402
from rewire.graph.store import GraphStore, result_rows, load_query  # noqa: E402
from rewire.execution import ExecutionCoordinator, canonical_hash  # noqa: E402


def http(base, path, method="GET", body=None, key=None, timeout=2):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if key:
        headers["Idempotency-Key"] = key
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def main():
    # Phase 1 creates a fresh, uniquely named graph and records ownership.
    discovery = run_phase1("base")
    graph_name, run_id = discovery["graphName"], discovery["runId"]
    store = GraphStore()
    graph = store.select(graph_name)
    coordinator = ExecutionCoordinator(store, graph_name, run_id)
    token = uuid.uuid4().hex[:12]
    plan_id, step_id = f"phase3:plan:{token}", f"phase3:step:{token}"
    effect_id = f"effect:shipment:{token}"
    operation_key = f"rewire:shipment:O-104:carrier-b:{token}"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="rewire-phase3-") as temp:
        db_path = Path(temp) / "provider.sqlite3"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "services" / "simulator")
        proc = subprocess.Popen([sys.executable, "-m", "rewire_simulator", "--host", "127.0.0.1",
            "--port", str(port), "--db", str(db_path), "--now-ms", "1792230600000",
            "--fault-after-commit", "booking"], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 12
            while True:
                if proc.poll() is not None:
                    raise RuntimeError("Phase 3 simulator exited before readiness")
                try:
                    if http(base, "/health")[0] == 200:
                        break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Phase 3 simulator did not become ready")
                    time.sleep(.1)

            _, order = http(base, "/v1/inventory/orders/O-104")
            _, reservation = http(base, "/v1/inventory/reservations/R81")
            shared = {"orderId": order["orderId"], "warehouseId": order["warehouseId"]}
            _, pickup = http(base, "/v1/carriers/carrier-b/pickup", "POST", shared, "p3:pickup")
            _, quote = http(base, "/v1/carriers/carrier-b/quote", "POST",
                {**shared, "pickupId": pickup["pickupId"]}, "p3:quote")
            _, label = http(base, "/v1/carriers/carrier-b/label", "POST",
                {**shared, "pickupId": pickup["pickupId"], "quoteId": quote["quoteId"]}, "p3:label")

            artifacts = [
                {"id": f"phase3:pickup:{token}", "typeId": "Pickup", "schemaVersion": "pickup-v1",
                 "version": 1, "status": pickup["status"], "expiresAt": 0, **shared,
                 "pickupId": pickup["pickupId"]},
                {"id": f"phase3:quote:{token}", "typeId": "Quote", "schemaVersion": "quote-v1",
                 "version": 1, "status": "READY", "expiresAt": quote["expiresAt"], **shared,
                 "quoteId": quote["quoteId"], "pickupId": quote["pickupId"],
                 "priceUnits": quote["priceUnits"]},
                {"id": f"phase3:label:{token}", "typeId": "Label", "schemaVersion": "label-v1",
                 "version": 1, "status": label["status"], "expiresAt": 0, **shared,
                 "labelId": label["labelId"], "quoteId": label["quoteId"]},
            ]
            graph.query("UNWIND $rows AS row CREATE (a:Artifact {id: row.id}) SET a = row "
                "WITH a MATCH (ty:ArtifactType {id:a.typeId}) CREATE (a)-[:INSTANCE_OF]->(ty) "
                "WITH a MATCH (r:Run {id:$runId}) CREATE (r)-[:HAS_ARTIFACT]->(a) RETURN count(a)",
                {"rows": artifacts, "runId": run_id})
            graph.query("MATCH (run:Run {id:$runId}) MATCH (t:ToolRevision {id:'tool:carrier-b-dispatch:v1'}) "
                "CREATE (run)-[:HAS_PLAN]->(p:Plan {id:$planId,basedOnRevision:1,status:'SELECTED',"
                "searchOutcome:'STRUCTURALLY_VALID',invalidReason:''}) "
                "CREATE (p)-[:HAS_STEP]->(s:PlanStep {id:$stepId,status:'READY',ordinal:1}) "
                "CREATE (s)-[:USES_TOOL]->(t) "
                "WITH run,p,s CREATE (run)-[:HAS_EFFECT]->(:Effect {id:$effectId,state:'FREE',activeIntentId:''}) "
                "SET run.selectedPlanId=p.id, run.stateRevision=2 "
                "CREATE (run)-[:EMITTED]->(:Event {id:$eventId,sequence:2,type:'plan.selected',timestamp:$nowMs,payloadJson:'{}'}) "
                "RETURN run.id", {"runId":run_id,"planId":plan_id,"stepId":step_id,
                    "effectId":effect_id,"eventId":f"event:p3-selected:{token}","nowMs":1792230600000})
            bindings = [
                ("slot:carrier-b-dispatch:reservation", "artifact:reservation:R81", 1),
                ("slot:carrier-b-dispatch:pickup", artifacts[0]["id"], 1),
                ("slot:carrier-b-dispatch:quote", artifacts[1]["id"], 1),
                ("slot:carrier-b-dispatch:label", artifacts[2]["id"], 1),
            ]
            graph.query("UNWIND $rows AS row MATCH (s:PlanStep {id:$stepId}) "
                "MATCH (a:Artifact {id:row.artifactId}) CREATE (s)-[:BINDS {slotId:row.slotId,expectedVersion:row.version}]->(a)",
                {"rows":[{"slotId":x,"artifactId":y,"version":z} for x,y,z in bindings],"stepId":step_id})

            params = {"runId":run_id,"planId":plan_id,"stepId":step_id,"expectedRevision":2}
            preflight = result_rows(graph.ro_query(load_query("Q06_execution_preflight"), params))
            if len(preflight) != 4:
                raise AssertionError(f"preflight must return all four requirement slots: {preflight}")
            expected_ids = {b[1] for b in bindings}
            for row in preflight:
                if (row["artifactId"] not in expected_ids or row["runArtifactId"] != row["artifactId"]
                    or row["artifactVersion"] != row["expectedVersion"]
                    or row["artifactSchemaVersion"] != row["requiredSchemaVersion"]
                    or row["artifactStatus"] != row["requiredStatus"]
                    or (row["expiresAt"] and row["expiresAt"] <= 1792230600000)):
                    raise AssertionError(f"preflight semantic validation failed: {row}")

            booking_payload = {**shared,"reservationId":reservation["reservationId"],
                "pickupId":pickup["pickupId"],"quoteId":quote["quoteId"],"labelId":label["labelId"]}
            payload_hash = canonical_hash(booking_payload)
            ids = {k:f"p3:{k}:{token}" for k in ("intentId","attemptId","receiptId","eventId")}
            # Stale revision must be a no-op.
            stale = coordinator.transition("Q08_claim_intent", {"runId":run_id,"planId":plan_id,
                "stepId":step_id,"effectId":effect_id,"expectedRevision":1,"adapterId":"adapter:carrier-b-dispatch",
                "intentId":ids["intentId"],"operationKey":operation_key,"payloadHash":payload_hash,
                "providerId":"carrier-b","nowMs":1792230600000,"eventId":"p3:stale",
                "eventPayloadJson":"{}"}, required=False)
            if stale:
                raise AssertionError("stale selected-plan revision unexpectedly claimed the effect")
            claim_params = {"runId":run_id,"planId":plan_id,"stepId":step_id,
                "effectId":effect_id,"expectedRevision":2,"adapterId":"adapter:carrier-b-dispatch",
                "intentId":ids["intentId"],"operationKey":operation_key,"payloadHash":payload_hash,
                "providerId":"carrier-b","nowMs":1792230600000,"eventId":ids["eventId"],
                "eventPayloadJson":"{}"}
            claim = coordinator.claim_intent(claim_params)
            replayed_claim = coordinator.claim_intent(claim_params)
            if claim["replayed"] or not replayed_claim["replayed"] or replayed_claim["intentId"] != ids["intentId"]:
                raise AssertionError("intent request retry did not return the original intent")
            attempt = coordinator.transition("Q08A_start_attempt",{"runId":run_id,"effectId":effect_id,
                "intentId":ids["intentId"],"expectedRevision":claim["revision"],"attemptId":ids["attemptId"],
                "nowMs":1792230600000,"eventId":"p3:attempt-start","eventPayloadJson":"{}"})

            try:
                http(base,"/v1/carriers/carrier-b/booking","POST",booking_payload,operation_key)
                raise AssertionError("fault injection should drop the response after booking commit")
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                pass
            unknown = coordinator.transition("Q08B_mark_unknown",{"runId":run_id,"effectId":effect_id,
                "intentId":ids["intentId"],"attemptId":ids["attemptId"],"expectedRevision":attempt["revision"],
                "nowMs":1792230600100,"eventId":"p3:unknown","eventPayloadJson":"{}"})
            fence = result_rows(graph.ro_query(load_query("Q07_effect_fence"),{"runId":run_id,"effectId":effect_id}))
            if not fence or fence[0]["effectState"] != "CLAIMED":
                raise AssertionError("unknown effect did not remain fenced")
            denied_replacement = coordinator.transition("Q08_claim_intent",{"runId":run_id,
                "planId":plan_id,"stepId":step_id,"effectId":effect_id,
                "expectedRevision":unknown["revision"],"adapterId":"adapter:carrier-b-dispatch",
                "intentId":f"p3:replacement:{token}","operationKey":f"replacement:{token}",
                "payloadHash":payload_hash,"providerId":"carrier-d","nowMs":1792230600150,
                "eventId":"p3:replacement-denied","eventPayloadJson":"{}"}, required=False)
            if denied_replacement:
                raise AssertionError("a second provider intent bypassed the logical effect fence")
            # Simulate coordinator process loss: close client and reconstruct from graph state.
            store.close()
            store = GraphStore(); graph = store.select(graph_name)
            coordinator = ExecutionCoordinator(store, graph_name, run_id)
            recovered = result_rows(graph.ro_query(load_query("Q09_inspect_intent"),
                {"runId":run_id,"intentId":ids["intentId"]}))
            if not recovered or recovered[0]["intentStatus"] != "UNKNOWN" or recovered[0]["operationKey"] != operation_key:
                raise AssertionError(f"restart did not recover original unknown intent: {recovered}")
            status_attempt = coordinator.transition("Q09A_start_status_attempt",{"runId":run_id,"effectId":effect_id,
                "intentId":ids["intentId"],"expectedRevision":unknown["revision"],"attemptId":"p3:status-attempt",
                "nowMs":1792230600200,"eventId":"p3:reconcile","eventPayloadJson":"{}"})
            status_code, status_doc = http(base,f"/v1/carriers/carrier-b/operations/{operation_key}")
            receipt_result = status_doc.get("result",{})
            expected_receipt = {key: booking_payload[key] for key in
                ("orderId", "reservationId", "pickupId", "quoteId", "labelId")}
            if (status_code != 200 or status_doc.get("status") != "CONFIRMED"
                or status_doc.get("operationKey") != operation_key
                or status_doc.get("providerId") != "carrier-b"
                or status_doc.get("operationType") != "booking"
                or any(receipt_result.get(key) != value for key, value in expected_receipt.items())
                or receipt_result.get("providerId") != "carrier-b"
                or receipt_result.get("status") != "CONFIRMED"
                or not receipt_result.get("bookingId")):
                raise AssertionError(f"provider status did not prove intended booking: {status_doc}")
            receipt = coordinator.transition("Q10_confirm_receipt",{"runId":run_id,"effectId":effect_id,
                "intentId":ids["intentId"],"statusAttemptId":"p3:status-attempt",
                "expectedRevision":status_attempt["revision"],"validatedPayloadHash":payload_hash,
                "receiptId":ids["receiptId"],"providerRecordId":receipt_result["bookingId"],
                "payloadDigest":canonical_hash(receipt_result),"nowMs":1792230600300,
                "eventId":"p3:confirmed","eventPayloadJson":"{}"})
            # Reconstruct after receipt persistence, before the output artifact is projected.
            store.close(); store = GraphStore(); graph = store.select(graph_name)
            coordinator = ExecutionCoordinator(store, graph_name, run_id)
            projection_params = {"runId":run_id,"effectId":effect_id,
                "intentId":ids["intentId"],"expectedRevision":receipt["revision"],"typeId":"Booking",
                "schemaVersion":"booking-v1","artifactId":f"artifact:booking:{receipt_result['bookingId']}",
                "providerRecordId":receipt_result["bookingId"],"orderId":"O-104","warehouseId":"W7",
                "nowMs":1792230600400,"eventId":"p3:projected","eventPayloadJson":"{}"}
            projected = coordinator.project_booking(projection_params)
            # Reconstruct again after projection commit to model a lost UI response.
            store.close(); store = GraphStore(); graph = store.select(graph_name)
            coordinator = ExecutionCoordinator(store, graph_name, run_id)
            projection_replay = coordinator.project_booking(projection_params)
            if projected["replayed"] or not projection_replay["replayed"]:
                raise AssertionError("booking artifact projection is not idempotent")
            # Exercise the authoritative-absence branch against an operation key
            # that was never submitted to this synchronous simulator.
            absent_key = f"p3:never-submitted:{token}"
            absent_code, _ = http(base,
                f"/v1/carriers/carrier-b/operations/{absent_key}")
            if absent_code != 404:
                raise AssertionError(f"simulator absence contract expected 404, got {absent_code}")
            no_effect_run = f"run:p3-no-effect:{token}"
            no_effect_intent = f"p3:no-effect-intent:{token}"
            no_effect_attempt = f"p3:no-effect-attempt:{token}"
            no_effect_effect = f"effect:no-effect:{token}"
            no_effect_step = f"p3:no-effect-step:{token}"
            graph.query("CREATE (r:Run {id:$runId,stateRevision:1,status:'RUNNING'}) "
                "CREATE (e:Effect {id:$effectId,state:'CLAIMED',activeIntentId:$intentId}) "
                "CREATE (i:Intent {id:$intentId,logicalEffectId:$effectId,operationKey:$operationKey,"
                "payloadHash:$payloadHash,status:'PREPARED',providerId:'carrier-b',createdAt:$nowMs}) "
                "CREATE (s:PlanStep {id:$stepId,status:'PREPARED',ordinal:1}) "
                "CREATE (r)-[:HAS_EFFECT]->(e),(e)-[:HAS_INTENT]->(i),"
                "(i)-[:FOR_STEP]->(s) RETURN r.id",
                {"runId":no_effect_run,"effectId":no_effect_effect,"intentId":no_effect_intent,
                 "operationKey":absent_key,"payloadHash":canonical_hash({"absentKey":absent_key}),
                 "stepId":no_effect_step,"nowMs":1792230600500})
            recovered_prepared = coordinator.transition("Q09A_start_status_attempt",{"runId":no_effect_run,
                "effectId":no_effect_effect,"intentId":no_effect_intent,"expectedRevision":1,
                "attemptId":no_effect_attempt,"nowMs":1792230600550,
                "eventId":"p3:prepared-reconcile","eventPayloadJson":"{}"})
            denied_absence = coordinator.transition("Q11_record_no_effect",{"runId":no_effect_run,
                "intentId":no_effect_intent,"statusAttemptId":no_effect_attempt,"expectedRevision":recovered_prepared["revision"],
                "providerAbsenceIsAuthoritative":False,"nowMs":1792230600600,
                "eventId":"p3:no-effect-denied","eventPayloadJson":"{}"},required=False)
            if denied_absence:
                raise AssertionError("unverified provider absence must not release effect fence")
            no_effect = coordinator.transition("Q11_record_no_effect",{"runId":no_effect_run,
                "intentId":no_effect_intent,"statusAttemptId":no_effect_attempt,"expectedRevision":recovered_prepared["revision"],
                "providerAbsenceIsAuthoritative":True,"nowMs":1792230600600,
                "eventId":"p3:no-effect-recorded","eventPayloadJson":"{}"})
            no_effect_state = result_rows(graph.ro_query(load_query("Q07_effect_fence"),
                {"runId":no_effect_run,"effectId":no_effect_effect}))
            if (no_effect["revision"] != recovered_prepared["revision"] + 1 or not no_effect_state
                or no_effect_state[0]["effectState"] != "FREE"
                or no_effect_state[0]["intentStatus"] != "NO_EFFECT"):
                raise AssertionError(f"authoritative no-effect transition failed: {no_effect_state}")
            final_rows = result_rows(graph.ro_query(load_query("Q13_read_projection"),{"runId":run_id}))
            event_sequences = sorted({r["eventSequence"] for r in final_rows if r.get("eventSequence") is not None})
            if (projected["runStatus"] != "SUCCEEDED" or not event_sequences
                or event_sequences != list(range(min(event_sequences), max(event_sequences)+1))):
                raise AssertionError(f"final event/projection invariant failed: {projected}, {final_rows}")
            verification = {"status":"PASS","graphName":graph_name,"runId":run_id,
                "checks":{"allRequiredBindingsPreflighted":True,"staleRevisionDenied":True,
                    "effectClaimedBeforeDispatch":True,"afterCommitResponseLoss":True,
                    "intentClaimRetryIsIdempotent":True,
                    "unknownEffectFenced":True,"coordinatorRestartRecoveredIntent":True,
                    "crossProviderReplacementDenied":True,
                    "statusLookupConfirmedOriginalOperation":True,"receiptHashMatchedIntent":True,
                    "bookingProjectedIntoGraph":True,"projectionRetryIsIdempotent":True,"runSucceeded":True,
                    "eventSequencesContiguous":True,"authoritativeNoEffectReleasesFence":True,
                    "nonAuthoritativeAbsenceDenied":True,"preparedIntentReconciledWithoutDispatch":True,
                    "receiptCommitSurvivesCoordinatorRestart":True,
                    "projectionCommitSurvivesCoordinatorRestart":True},
                "intent":{"id":ids["intentId"],"operationKey":operation_key,
                    "payloadHash":payload_hash,"status":"CONFIRMED"},
                "booking":receipt_result,"revision":projected["revision"],
                "eventSequences":event_sequences,"createdAtUtc":datetime.now(timezone.utc).isoformat()}
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
            if store: store.close()
        from rewire_simulator.store import FaultController, ProviderWorld
        audit = ProviderWorld(db_path,1792230600000,FaultController()).evaluator_audit()
        if audit["rowCounts"]["bookings"] != 1:
            raise AssertionError(f"expected one provider-side booking: {audit}")
        verification["evaluatorWorldAudit"] = audit
        target = ROOT / "reports" / "phase-03" / "verification.json"
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(verification,indent=2,sort_keys=True),encoding="utf-8")
        verification["reportPath"] = str(target)
        print(json.dumps(verification,indent=2,sort_keys=True))


if __name__ == "__main__":
    main()
