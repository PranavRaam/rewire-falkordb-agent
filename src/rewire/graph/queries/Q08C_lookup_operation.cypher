MATCH (run:Run {id: $runId})-[:HAS_EFFECT]->(effect:Effect {id: $effectId})
MATCH (effect)-[:HAS_INTENT]->(intent:Intent {operationKey: $operationKey})
OPTIONAL MATCH (intent)-[:FOR_STEP]->(step:PlanStep)
RETURN effect.id AS effectId, effect.state AS effectState,
       effect.activeIntentId AS activeIntentId, intent.id AS intentId,
       intent.operationKey AS operationKey, intent.payloadHash AS payloadHash,
       intent.providerId AS providerId, intent.status AS intentStatus,
       step.id AS stepId
