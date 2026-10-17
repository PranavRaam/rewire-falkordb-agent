MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect)-[:HAS_INTENT]->(i:Intent {id: $intentId})
OPTIONAL MATCH (i)-[:HAS_ATTEMPT]->(a:Attempt)
OPTIONAL MATCH (receipt:Receipt)-[:CONFIRMS]->(i)
RETURN effect.id AS effectId, effect.state AS effectState,
       i.operationKey AS operationKey, i.payloadHash AS payloadHash,
       i.providerId AS providerId, i.status AS intentStatus,
       a.id AS attemptId, a.outcome AS attemptOutcome,
       receipt.id AS receiptId, receipt.providerRecordId AS providerRecordId
ORDER BY attemptId, receiptId
