MATCH (run:Run {id: $runId})-[:HAS_GOAL]->(goal:Goal)
OPTIONAL MATCH (run)-[:HAS_EFFECT]->(effect:Effect)
OPTIONAL MATCH (effect)-[:HAS_INTENT]->(intent:Intent)
RETURN run.id AS runId, run.status AS runStatus,
       run.stateRevision AS revision, run.catalogRevision AS catalogRevision,
       run.selectedPlanId AS selectedPlanId,
       goal.id AS goalId, goal.outputTypeId AS outputType,
       goal.orderId AS orderId, goal.warehouseId AS warehouseId,
       goal.destinationZone AS destinationZone, goal.weightKg AS weightKg,
       goal.maxCostUnits AS maxCostUnits, goal.cutoffAt AS cutoffAt,
       effect.id AS effectId, effect.state AS effectState,
       intent.id AS intentId, intent.status AS intentStatus,
       intent.operationKey AS operationKey
ORDER BY effect.id
