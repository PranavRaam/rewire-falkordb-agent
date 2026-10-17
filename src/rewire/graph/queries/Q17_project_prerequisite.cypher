MATCH (r:Run {id:$runId})-[:HAS_EFFECT]->(:Effect)-[:HAS_INTENT]->(i:Intent {id:$intentId})
MATCH (receipt:Receipt)-[:CONFIRMS]->(i)
MATCH (ty:ArtifactType {id:$typeId})
WHERE r.stateRevision=$expectedRevision AND i.status='CONFIRMED'
MERGE (a:Artifact {id:$artifactId})
ON CREATE SET a += $properties
MERGE (r)-[:HAS_ARTIFACT]->(a)
MERGE (a)-[:INSTANCE_OF]->(ty)
MERGE (receipt)-[:PROJECTS]->(a)
SET r.stateRevision=r.stateRevision+1
CREATE (r)-[:EMITTED]->(:Event {id:$eventId,sequence:r.stateRevision,type:'artifact.observed',timestamp:$nowMs,payloadJson:$eventPayloadJson})
RETURN a.id AS artifactId,r.stateRevision AS revision
