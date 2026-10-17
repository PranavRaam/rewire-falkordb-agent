MATCH (run:Run {id: $runId})
OPTIONAL MATCH (run)-[:HAS_EFFECT]->(effect:Effect)
OPTIONAL MATCH (effect)-[:HAS_INTENT]->(intent:Intent)
OPTIONAL MATCH (intent)-[:HAS_ATTEMPT]->(attempt:Attempt)
OPTIONAL MATCH (receipt:Receipt)-[:CONFIRMS]->(intent)
OPTIONAL MATCH (receipt)-[:PROJECTS]->(artifact:Artifact)
OPTIONAL MATCH (run)-[:EMITTED]->(event:Event)
RETURN run.id AS runId, run.status AS runStatus,
       run.stateRevision AS revision, effect.state AS effectState,
       intent.id AS intentId, intent.status AS intentStatus,
       intent.operationKey AS operationKey, intent.payloadHash AS payloadHash,
       attempt.id AS attemptId, attempt.outcome AS attemptOutcome,
       receipt.id AS receiptId, receipt.providerRecordId AS providerRecordId,
       artifact.id AS artifactId, event.sequence AS eventSequence,
       event.type AS eventType
ORDER BY eventSequence, attemptId
