MATCH (run:Run {id: $runId})-[:HAS_PLAN]->(p:Plan {id: $planId})
MATCH (run)-[:HAS_EFFECT]->(effect:Effect {id: $effectId})
MATCH (p)-[:HAS_STEP]->(step:PlanStep {id: $stepId})-[:USES_TOOL]->(t:ToolRevision)
WHERE run.stateRevision = $expectedRevision
  AND run.selectedPlanId = p.id AND p.status = 'SELECTED'
  AND step.status = 'READY' AND t.enabled = true
  AND t.catalogRevision = run.catalogRevision AND effect.state = 'FREE'
  AND t.adapterId = $adapterId
CREATE (i:Intent {
  id: $intentId, logicalEffectId: $effectId, operationKey: $operationKey,
  payloadHash: $payloadHash, status: 'PREPARED', providerId: $providerId,
  createdAt: $nowMs, payloadJson: $payloadJson
})
CREATE (effect)-[:HAS_INTENT]->(i)
CREATE (i)-[:FOR_STEP]->(step)
CREATE (step)-[:AUTHORIZED_BY]->(i)
SET effect.state = 'CLAIMED', effect.activeIntentId = i.id,
    step.status = 'PREPARED', run.status = 'RUNNING',
    run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'intent.prepared',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN i.id AS intentId, run.stateRevision AS revision, e.id AS eventId
