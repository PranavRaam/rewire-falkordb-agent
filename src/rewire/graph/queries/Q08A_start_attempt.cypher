MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect {id: $effectId})
MATCH (effect)-[:HAS_INTENT]->(i:Intent {id: $intentId})
MATCH (i)-[:FOR_STEP]->(step:PlanStep)
WHERE run.stateRevision = $expectedRevision
  AND effect.state = 'CLAIMED' AND effect.activeIntentId = i.id
  AND i.status = 'PREPARED' AND step.status = 'PREPARED'
CREATE (attempt:Attempt {
  id: $attemptId, startedAt: $nowMs, endedAt: 0,
  outcome: 'IN_FLIGHT'
})
CREATE (i)-[:HAS_ATTEMPT]->(attempt)
SET i.status = 'IN_FLIGHT', step.status = 'IN_FLIGHT',
    run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'effect.attempt_started',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN attempt.id AS attemptId, i.id AS intentId,
       run.stateRevision AS revision, e.id AS eventId
