MATCH (run:Run {id: $runId})-[:HAS_ARTIFACT]->(a:Artifact {id: $artifactId})
MATCH (a)-[:INSTANCE_OF]->(ty:ArtifactType {id: $typeId})
WHERE run.stateRevision = $expectedRevision
  AND a.version = $expectedArtifactVersion
  AND a.schemaVersion = $schemaVersion
  AND a.status = $requiredStatus
  AND (a.expiresAt = 0 OR a.expiresAt > $nowMs)
  AND a.orderId = $orderId
  AND a.warehouseId = $warehouseId
RETURN a.id AS artifactId, a.typeId AS typeId, a.schemaVersion AS schemaVersion,
       a.version AS version, a.status AS status, a.expiresAt AS expiresAt,
       a.orderId AS orderId, a.warehouseId AS warehouseId
