MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect {id: $effectId})
MATCH (effect)-[:HAS_INTENT]->(i:Intent {id: $intentId})
MATCH (i)-[:FOR_STEP]->(step:PlanStep)
MATCH (receipt:Receipt)-[:CONFIRMS]->(i)
MATCH (ty:ArtifactType {id: $typeId})
WHERE run.stateRevision = $expectedRevision
  AND effect.state = 'CONFIRMED' AND i.status = 'CONFIRMED'
  AND receipt.status = 'CONFIRMED' AND receipt.providerRecordId = $providerRecordId
MERGE (a:Artifact {id: $artifactId})
ON CREATE SET a.typeId = $typeId, a.schemaVersion = $schemaVersion,
  a.version = 1, a.status = 'CONFIRMED', a.expiresAt = 0,
  a.orderId = $orderId, a.warehouseId = $warehouseId,
  a.bookingId = $providerRecordId
WITH run, effect, i, step, receipt, a, ty
WHERE a.typeId = $typeId AND a.schemaVersion = $schemaVersion
  AND a.orderId = $orderId AND a.warehouseId = $warehouseId
  AND a.bookingId = $providerRecordId
MERGE (run)-[:HAS_ARTIFACT]->(a)
MERGE (a)-[:INSTANCE_OF]->(ty)
MERGE (receipt)-[:PROJECTS]->(a)
WITH run, a
WHERE run.stateRevision = $expectedRevision
  AND run.status <> 'SUCCEEDED'
SET run.status = 'SUCCEEDED', run.stateRevision = run.stateRevision + 1
CREATE (run)-[:EMITTED]->(e:Event {
  id: $eventId, sequence: run.stateRevision, type: 'run.succeeded',
  timestamp: $nowMs, payloadJson: $eventPayloadJson
})
RETURN a.id AS artifactId, run.status AS runStatus,
       run.stateRevision AS revision, e.id AS eventId
