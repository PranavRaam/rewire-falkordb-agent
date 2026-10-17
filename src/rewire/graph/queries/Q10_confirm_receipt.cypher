MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect)-[:HAS_INTENT]->(i:Intent {id: $intentId})
MATCH (i)-[:FOR_STEP]->(step:PlanStep)
MATCH (i)-[:HAS_ATTEMPT]->(a:Attempt {id: $statusAttemptId})
WHERE run.stateRevision = $expectedRevision
  AND effect.state = 'CLAIMED' AND effect.activeIntentId = i.id
  AND i.status IN ['PREPARED', 'IN_FLIGHT', 'UNKNOWN', 'INVALID_OUTPUT']
  AND i.payloadHash = $validatedPayloadHash
CREATE (receipt:Receipt {
  id: $receiptId, providerRecordId: $providerRecordId,
  payloadDigest: $payloadDigest, observedAt: $nowMs, status: 'CONFIRMED'
})
CREATE (a)-[:OBSERVED]->(receipt)
CREATE (receipt)-[:CONFIRMS]->(i)
SET i.status = 'CONFIRMED', effect.state = 'CONFIRMED',
    a.outcome = 'CONFIRMED', a.endedAt = $nowMs,
    step.status = 'CONFIRMED', run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'effect.confirmed',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN receipt.id AS receiptId, i.id AS intentId,
       run.stateRevision AS revision, e.id AS eventId
