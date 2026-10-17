MATCH (run:Run {id: $runId})-[:HAS_PLAN]->(p:Plan {id: $planId})
MATCH (p)-[:HAS_STEP]->(step:PlanStep {id: $stepId})-[:USES_TOOL]->(t:ToolRevision)
WHERE run.stateRevision = $expectedRevision
  AND run.selectedPlanId = p.id AND p.status = 'SELECTED'
  AND step.status = 'READY' AND t.enabled = true
  AND t.catalogRevision = run.catalogRevision
OPTIONAL MATCH (t)-[:REQUIRES]->(slot:RequirementSlot)-[:OF_TYPE]->(ty:ArtifactType)
OPTIONAL MATCH (step)-[binding:BINDS]->(a:Artifact)
WHERE binding.slotId = slot.id
OPTIONAL MATCH (run)-[:HAS_ARTIFACT]->(member:Artifact)
WHERE member.id = a.id
RETURN run.stateRevision AS revision, t.id AS toolId, t.toolId AS publicToolId,
       t.adapterId AS adapterId, t.enabled AS toolEnabled,
       slot.id AS slotId, slot.name AS slotName, slot.cardinality AS cardinality,
       slot.schemaVersion AS requiredSchemaVersion, slot.minVersion AS minVersion,
       slot.requiredStatus AS requiredStatus, slot.scopeOrder AS scopeOrder,
       slot.scopeWarehouse AS scopeWarehouse, ty.id AS requiredTypeId,
       binding.slotId AS boundSlotId, binding.expectedVersion AS expectedVersion,
       a.id AS artifactId, a.typeId AS artifactTypeId,
       a.schemaVersion AS artifactSchemaVersion, a.version AS artifactVersion,
       a.status AS artifactStatus, a.expiresAt AS expiresAt,
       a.orderId AS artifactOrderId, a.warehouseId AS artifactWarehouseId,
       member.id AS runArtifactId
ORDER BY slotId, artifactId
