MATCH (t:ToolRevision)-[:PRODUCES]->(out:ArtifactType {id: $typeId})
WHERE t.enabled = true
  AND t.catalogRevision = $catalogRevision
  AND (t.maxWeightKg = 0 OR t.maxWeightKg >= $weightKg)
OPTIONAL MATCH (t)-[:REQUIRES]->(slot:RequirementSlot)-[:OF_TYPE]->(input:ArtifactType)
OPTIONAL MATCH (t)-[:CONSUMES]->(consumedType:ArtifactType)
RETURN t.id AS toolId, t.toolId AS publicToolId, t.version AS toolVersion,
       t.enabled AS enabled, t.maxWeightKg AS maxWeightKg,
       t.adapterId AS adapterId, t.effectClass AS effectClass,
       t.outputBindingsJson AS outputBindingsJson,
       slot.id AS slotId, slot.name AS slotName, input.id AS inputTypeId,
       consumedType.id AS consumedTypeId,
       slot.cardinality AS cardinality, slot.schemaVersion AS schemaVersion,
       slot.minVersion AS minVersion, slot.requiredStatus AS requiredStatus,
       slot.scopeOrder AS scopeOrder, slot.scopeWarehouse AS scopeWarehouse,
       slot.ruleId AS ruleId, slot.outputBindingsJson AS slotOutputBindingsJson
ORDER BY toolId, slotId
