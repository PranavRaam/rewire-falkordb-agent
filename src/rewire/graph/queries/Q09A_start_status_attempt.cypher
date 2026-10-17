MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect {id: $effectId})
MATCH (effect)-[:HAS_INTENT]->(i:Intent {id: $intentId})
MATCH (i)-[:FOR_STEP]->(:PlanStep)
WHERE run.stateRevision = $expectedRevision
  AND effect.state = 'CLAIMED' AND effect.activeIntentId = i.id
  AND i.status IN ['PREPARED', 'IN_FLIGHT', 'UNKNOWN']
CREATE (attempt:Attempt {
  id: $attemptId, startedAt: $nowMs, endedAt: 0,
  outcome: 'STATUS_LOOKUP_PENDING'
})
CREATE (i)-[:HAS_ATTEMPT]->(attempt)
SET run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'effect.reconciliation_started',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN attempt.id AS attemptId, i.id AS intentId,
       run.stateRevision AS revision, e.id AS eventId
