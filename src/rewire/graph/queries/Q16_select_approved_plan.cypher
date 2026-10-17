MATCH (r:Run {id:$runId})
WHERE r.stateRevision=$expectedRevision AND r.selectedPlanId=''
CREATE (r)-[:HAS_PLAN]->(p:Plan {id:$planId,status:'SELECTED',basedOnRevision:$expectedRevision,
  approvalDigest:$digest,snapshotJson:$snapshot,searchOutcome:'STRUCTURALLY_VALID',invalidReason:''})
SET r.selectedPlanId=p.id,r.stateRevision=r.stateRevision+1
CREATE (r)-[:EMITTED]->(:Event {id:$eventId,sequence:r.stateRevision,type:'plan.approved',timestamp:$nowMs,payloadJson:$snapshot})
RETURN r.stateRevision AS revision
