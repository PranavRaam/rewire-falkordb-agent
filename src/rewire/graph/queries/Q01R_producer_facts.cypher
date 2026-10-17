MATCH (t:ToolRevision)-[:PRODUCES]->(:ArtifactType {id: $typeId})
WHERE t.catalogRevision = $catalogRevision
RETURN t.id AS toolId, t.version AS toolVersion,
       t.enabled AS enabled, t.maxWeightKg AS maxWeightKg
ORDER BY toolId
