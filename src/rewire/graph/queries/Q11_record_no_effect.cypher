MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect)-[:HAS_INTENT]->(i:Intent {id: $intentId})
MATCH (i)-[:FOR_STEP]->(step:PlanStep)
MATCH (i)-[:HAS_ATTEMPT]->(a:Attempt {id: $statusAttemptId})
WHERE run.stateRevision = $expectedRevision
  AND effect.state = 'CLAIMED' AND effect.activeIntentId = i.id
  AND i.status IN ['PREPARED', 'IN_FLIGHT', 'UNKNOWN']
  AND $providerAbsenceIsAuthoritative = true
  AND a.outcome = 'STATUS_LOOKUP_PENDING'
SET i.status = 'NO_EFFECT', effect.state = 'FREE', effect.activeIntentId = '',
    step.status = 'READY', a.outcome = 'NO_EFFECT', a.endedAt = $nowMs,
    run.status = 'RUNNING', run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'effect.no_effect',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN i.id AS intentId, effect.state AS effectState,
       run.stateRevision AS revision, e.id AS eventId
