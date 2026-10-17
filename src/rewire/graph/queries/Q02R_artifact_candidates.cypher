MATCH (run:Run {id: $runId})-[:HAS_ARTIFACT]->(a:Artifact)
MATCH (a)-[:INSTANCE_OF]->(ty:ArtifactType {id: $typeId})
RETURN a.id AS artifactId, a.typeId AS typeId, a.schemaVersion AS schemaVersion,
       a.version AS version, a.status AS status, a.expiresAt AS expiresAt,
       a.orderId AS orderId, a.warehouseId AS warehouseId
ORDER BY artifactId
