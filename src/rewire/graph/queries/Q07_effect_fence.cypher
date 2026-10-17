MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect {id: $effectId})
OPTIONAL MATCH (effect)-[:HAS_INTENT]->(i:Intent)
RETURN effect.state AS effectState, effect.activeIntentId AS activeIntentId,
       i.id AS intentId, i.status AS intentStatus, i.operationKey AS operationKey,
       i.providerId AS providerId
