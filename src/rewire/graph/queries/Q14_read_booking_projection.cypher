MATCH (run:Run {id: $runId})-[:HAS_ARTIFACT]->(a:Artifact {id: $artifactId})
MATCH (a)-[:INSTANCE_OF]->(:ArtifactType {id: $typeId})
MATCH (receipt:Receipt {providerRecordId: $providerRecordId})-[:PROJECTS]->(a)
RETURN run.status AS runStatus, run.stateRevision AS revision,
       a.id AS artifactId, a.typeId AS typeId,
       a.schemaVersion AS schemaVersion, a.orderId AS orderId,
       a.warehouseId AS warehouseId, a.bookingId AS bookingId,
       receipt.status AS receiptStatus
