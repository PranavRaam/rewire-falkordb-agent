MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect {id: $effectId})
MATCH (effect)-[:HAS_INTENT]->(i:Intent {id: $intentId})
MATCH (i)-[:FOR_STEP]->(step:PlanStep)
MATCH (i)-[:HAS_ATTEMPT]->(attempt:Attempt {id: $attemptId})
WHERE run.stateRevision = $expectedRevision
  AND effect.state = 'CLAIMED' AND effect.activeIntentId = i.id
  AND i.status = 'IN_FLIGHT' AND attempt.outcome = 'IN_FLIGHT'
SET i.status = 'UNKNOWN', step.status = 'UNKNOWN',
    attempt.outcome = 'UNKNOWN', attempt.endedAt = $nowMs,
    run.status = 'PAUSED_UNKNOWN', run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'effect.unknown',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN i.id AS intentId, effect.state AS effectState,
       run.stateRevision AS revision, e.id AS eventId
