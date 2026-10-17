MATCH (run:Run {id: $runId})
MATCH (t:ToolRevision {id: $toolId})-[:REQUIRES]->(slot:RequirementSlot)-[:OF_TYPE]->(ty:ArtifactType)
WHERE t.enabled = true AND t.catalogRevision = run.catalogRevision
OPTIONAL MATCH (run)-[:HAS_ARTIFACT]->(a:Artifact)-[:INSTANCE_OF]->(ty)
WHERE a.schemaVersion = slot.schemaVersion
  AND a.version >= slot.minVersion
  AND (slot.requiredStatus = '*' OR a.status = slot.requiredStatus)
  AND (a.expiresAt = 0 OR a.expiresAt > $nowMs)
  AND (slot.scopeOrder = false OR a.orderId = $orderId)
  AND (slot.scopeWarehouse = false OR a.warehouseId = $warehouseId)
RETURN slot.id AS slotId, slot.name AS slotName, ty.id AS typeId,
       a.id AS artifactId, a.version AS artifactVersion
ORDER BY slotId, artifactId
