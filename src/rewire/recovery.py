"""Approved, resumable recovery for the synthetic carrier adapter.

One coordinator process owns execution. Approval is supplied by the trusted CLI
host, never inferred from model text. Provider status is checked before replay.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from typing import Any

from rewire.execution import ExecutionCoordinator, canonical_hash
from rewire.graph.store import GraphStore, result_rows

EXECUTION_LOCK = threading.RLock()
ADAPTERS = {f"adapter:carrier-{carrier}-{action}": (f"carrier-{carrier}", operation)
            for carrier in ("b", "d") for action, operation in
            (("pickup", "pickup"), ("quote", "quote"), ("label", "label"), ("dispatch", "booking"))}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("provider redirects are not allowed")


class SimulatorClient:
    def __init__(self, base: str):
        url = urlsplit(base)
        if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1")
                or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("only a loopback synthetic provider endpoint is supported")
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, path: str, payload=None, key=None):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        request = urllib.request.Request(self.base + path,
            data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        try:
            with self.opener.open(request, timeout=5) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ValueError("provider response exceeds limit")
                return response.status, json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return 404, {}
            raise

    def now(self):
        code, value = self.call("/v1/time")
        if code != 200 or value.get("clockMode") != "controlled-frozen":
            raise ValueError("expected a controlled synthetic provider clock")
        return int(value["nowMs"])


def preview_recovery(graph_name: str, run_id: str, now_ms: int) -> dict[str, Any]:
    from rewire.mcp_server import discover_recovery
    result = discover_recovery(graph_name, run_id, now_ms)
    snapshot = {key: result[key] for key in ("runId", "basedOnRevision", "goal", "steps", "preservedArtifacts")}
    snapshot.update(graphName=graph_name, nowMs=now_ms)
    if result["status"] != "STRUCTURALLY_VALID" or not snapshot["steps"]:
        raise ValueError("no structurally valid recovery to approve")
    if any(step["adapterId"] not in ADAPTERS for step in snapshot["steps"]):
        raise ValueError("plan requires an unsupported adapter")
    return {"status": "AWAITING_APPROVAL", "approvalDigest": canonical_hash(snapshot),
            "snapshot": snapshot, "queryEvidence": result["queryEvidence"]}


class RecoverySession:
    def __init__(self, graph_name: str, run_id: str, provider_url: str):
        self.store = GraphStore()
        self.graph_name, self.run_id = graph_name, run_id
        self.graph = self.store.select(graph_name)
        self.coordinator = ExecutionCoordinator(self.store, graph_name, run_id)
        self.provider = SimulatorClient(provider_url)

    def close(self):
        self.store.close()

    def rows(self, text, **params):
        return result_rows(self.graph.ro_query(text, {"runId": self.run_id, **params}))

    def revision(self):
        return self.rows("MATCH (r:Run {id:$runId}) RETURN r.stateRevision AS revision")[0]["revision"]

    def params(self, **values):
        return {"runId": self.run_id, "expectedRevision": self.revision(),
                "nowMs": self.provider.now(), "eventId": ExecutionCoordinator.ids("event")["eventId"],
                "eventPayloadJson": "{}", **values}

    def execute(self, approved_digest: str):
        with EXECUTION_LOCK:
            return self._execute(approved_digest)

    def _execute(self, approved_digest):
        existing = self.rows("MATCH (r:Run {id:$runId})-[:HAS_PLAN]->(p:Plan) "
            "WHERE r.selectedPlanId=p.id RETURN p.id AS id,p.approvalDigest AS digest,p.snapshotJson AS snapshot")
        if existing:
            if existing[0]["digest"] != approved_digest:
                raise ValueError("approval does not match the selected plan")
            snapshot = json.loads(existing[0]["snapshot"])
            plan_id = existing[0]["id"]
        else:
            preview = preview_recovery(self.graph_name, self.run_id, self.provider.now())
            if preview["approvalDigest"] != approved_digest:
                raise ValueError("approval is stale or does not match the current graph and clock")
            snapshot = preview["snapshot"]
            plan_id = f"plan:{approved_digest}"
            self.coordinator.transition("Q16_select_approved_plan", self.params(
                expectedRevision=snapshot["basedOnRevision"], planId=plan_id, digest=approved_digest,
                snapshot=json.dumps(snapshot, sort_keys=True)))
        if canonical_hash(snapshot) != approved_digest:
            raise ValueError("persisted approval snapshot has changed")
        outputs = {}
        for step in snapshot["steps"]:
            output = self._step(plan_id, snapshot, step, outputs)
            if output.get("status") == "RECONCILIATION_REQUIRED":
                return output
            outputs[step["id"]] = output
        booking = outputs[snapshot["steps"][-1]["id"]]
        return {"status": "SUCCEEDED", "approvalDigest": approved_digest,
                "booking": booking, "source": "validated provider receipts persisted in FalkorDB"}

    def _step(self, plan_id, snapshot, step, outputs):
        step_id = f"{plan_id}:{step['ordinal']}"
        intent_id, effect_id = f"{step_id}:intent", f"{step_id}:effect"
        prior = self.rows("MATCH (r:Run {id:$runId})-[:HAS_EFFECT]->(:Effect)-[:HAS_INTENT]->"
            "(i:Intent {id:$intentId}) MATCH (receipt:Receipt)-[:CONFIRMS]->(i) "
            "MATCH (receipt)-[:PROJECTS]->(a:Artifact) RETURN a.id AS id,a.responseJson AS response",
            intentId=intent_id)
        if prior and prior[0]["response"]:
            return {"artifactId": prior[0]["id"], **json.loads(prior[0]["response"])}
        provider_id, operation = ADAPTERS[step["adapterId"]]
        goal = snapshot["goal"]
        now = self.provider.now()
        existing_intent = self.rows("MATCH (r:Run {id:$runId})-[:HAS_EFFECT]->(:Effect)-[:HAS_INTENT]->"
            "(i:Intent {id:$intentId}) OPTIONAL MATCH (i)-[:HAS_ATTEMPT]->(a:Attempt) "
            "RETURN i.status AS status,i.payloadJson AS payload,count(a) AS attemptCount", intentId=intent_id)
        safe_prepared_replay = bool(existing_intent and existing_intent[0]["status"] == "PREPARED"
                                    and existing_intent[0]["attemptCount"] == 0)
        if existing_intent:
            # Reconciliation must remain possible after the original inputs expire.
            payload = json.loads(existing_intent[0]["payload"])
        else:
            if now >= goal["cutoff_at"]:
                raise ValueError("goal cutoff has passed")
            self.graph.query("MATCH (r:Run {id:$runId})-[:HAS_PLAN]->(p:Plan {id:$planId}) "
                "MATCH (t:ToolRevision {id:$toolId}) MERGE (p)-[:HAS_STEP]->(s:PlanStep {id:$stepId}) "
                "ON CREATE SET s.status='READY',s.ordinal=$ordinal "
                "MERGE (s)-[:USES_TOOL]->(t) MERGE (r)-[:HAS_EFFECT]->"
                "(:Effect {id:$effectId,state:'FREE',activeIntentId:''})",
                {"runId": self.run_id,"planId":plan_id,"toolId":step["toolId"],"stepId":step_id,
                 "ordinal":step["ordinal"],"effectId":effect_id})
            payload = {"orderId": goal["order_id"], "warehouseId": goal["warehouse_id"]}
            for binding in step["inputs"]:
                artifact_id = binding.get("artifactId") or outputs[binding["producerStepId"]]["artifactId"]
                artifact = self.rows("MATCH (r:Run {id:$runId})-[:HAS_ARTIFACT]->(a:Artifact {id:$id}) "
                    "RETURN properties(a) AS data", id=artifact_id)[0]["data"]
                for key in ("reservationId", "pickupId", "quoteId", "labelId"):
                    if artifact.get(key):
                        if key in payload and payload[key] != artifact[key]:
                            raise ValueError("conflicting prerequisite provenance")
                        payload[key] = artifact[key]
                self.graph.query("MATCH (s:PlanStep {id:$stepId}),(a:Artifact {id:$artifactId}) "
                    "MERGE (s)-[b:BINDS {slotId:$slotId}]->(a) SET b.expectedVersion=$version",
                    {"stepId":step_id,"artifactId":artifact_id,"slotId":binding["slotId"],
                     "version":binding.get("artifactVersion", artifact["version"])})
            preflight = self.coordinator.read("Q06_execution_preflight", self.params(planId=plan_id,stepId=step_id))
            if len(preflight) != len(step["inputs"]) or not preflight:
                raise ValueError("preflight did not return every required binding")
            for row in preflight:
                if (row["cardinality"] != 1 or row["runArtifactId"] != row["artifactId"]
                    or row["artifactVersion"] != row["expectedVersion"]
                    or row["artifactVersion"] < row["minVersion"]
                    or row["artifactTypeId"] != row["requiredTypeId"]
                    or row["artifactSchemaVersion"] != row["requiredSchemaVersion"]
                    or (row["requiredStatus"] != "*" and row["artifactStatus"] != row["requiredStatus"])
                    or (row["expiresAt"] and row["expiresAt"] <= now)
                    or (row["scopeOrder"] and row["artifactOrderId"] != goal["order_id"])
                    or (row["scopeWarehouse"] and row["artifactWarehouseId"] != goal["warehouse_id"])):
                    raise ValueError("binding failed current graph preflight")
        operation_key = "rewire:" + canonical_hash({"graph":self.graph_name,"step":step_id})
        common = dict(planId=plan_id,stepId=step_id,effectId=effect_id,intentId=intent_id)
        if not existing_intent:
            self.coordinator.claim_intent(self.params(**common,adapterId=step["adapterId"],
                operationKey=operation_key,payloadHash=canonical_hash(payload),providerId=provider_id,
                payloadJson=json.dumps(payload,sort_keys=True)))
        code, document = self.provider.call(f"/v1/carriers/{provider_id}/operations/{operation_key}")
        if code == 404:
            if existing_intent and not safe_prepared_replay:
                return {"status":"RECONCILIATION_REQUIRED","intentId":intent_id,
                        "reason":"No confirmed provider status; automatic redispatch is disabled."}
            attempt_id = ExecutionCoordinator.ids("attempt")["attemptId"]
            self.coordinator.transition("Q08A_start_attempt", self.params(**common,attemptId=attempt_id))
            try:
                self.provider.call(f"/v1/carriers/{provider_id}/{operation}",payload,operation_key)
            except (OSError, ConnectionError, TimeoutError):
                self.coordinator.transition("Q08B_mark_unknown", self.params(**common,attemptId=attempt_id))
            code, document = self.provider.call(f"/v1/carriers/{provider_id}/operations/{operation_key}")
        if code != 200:
            return {"status":"RECONCILIATION_REQUIRED","intentId":intent_id}
        result = document.get("result", {})
        record_key = operation + "Id"
        expected = {key: value for key, value in payload.items() if key != "warehouseId"}
        if operation == "label":
            expected.pop("pickupId", None)  # label receipt binds its quote; quote binds pickup
        if (document.get("operationKey") != operation_key or document.get("providerId") != provider_id
            or document.get("operationType") != operation or document.get("status") != "CONFIRMED"
            or not isinstance(result.get(record_key), str)
            or any(result.get(key) != value for key,value in expected.items())
            or (operation == "booking" and (result.get("providerId") != provider_id or result.get("status") != "CONFIRMED"))
            or (operation == "quote" and (result.get("priceUnits", float("inf")) > goal["max_cost_units"]
                or result.get("expiresAt", 0) <= now))):
            raise ValueError("provider receipt failed identity, provenance, or budget validation")
        status = self.rows("MATCH (i:Intent {id:$id}) RETURN i.status AS status",id=intent_id)[0]["status"]
        if status != "CONFIRMED":
            status_id = ExecutionCoordinator.ids("status")["attemptId"]
            self.coordinator.transition("Q09A_start_status_attempt", self.params(**common,attemptId=status_id))
            self.coordinator.transition("Q10_confirm_receipt", self.params(**common,statusAttemptId=status_id,
                validatedPayloadHash=canonical_hash(payload),receiptId=f"{intent_id}:receipt",
                providerRecordId=result[record_key],payloadDigest=canonical_hash(result)))
        artifact_id = f"artifact:{operation}:{result[record_key]}"
        type_id = step["expectedOutputType"]
        schema = self.rows("MATCH (t:ToolRevision {id:$id})-[:PRODUCES]->(ty:ArtifactType) RETURN ty.schemaVersion AS schema",id=step["toolId"])[0]["schema"]
        properties = {**payload,**result,"typeId":type_id,"schemaVersion":schema,"version":1,
            "status":result.get("status","READY"),"expiresAt":result.get("expiresAt",0),
            "responseJson":json.dumps(result,sort_keys=True)}
        if operation == "booking":
            self.coordinator.project_booking(self.params(**common,typeId=type_id,schemaVersion=schema,
                artifactId=artifact_id,providerRecordId=result[record_key],orderId=goal["order_id"],warehouseId=goal["warehouse_id"]))
            self.graph.query("MATCH (a:Artifact {id:$id}) SET a.responseJson=$response",
                {"id":artifact_id,"response":json.dumps(result,sort_keys=True)})
        else:
            self.coordinator.transition("Q17_project_prerequisite",self.params(**common,typeId=type_id,
                artifactId=artifact_id,properties=properties))
        return {"artifactId":artifact_id,**result}
