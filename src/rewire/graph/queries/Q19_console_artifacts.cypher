MATCH (r:Run {id: $runId})-[:HAS_ARTIFACT]->(a:Artifact)
RETURN properties(a) AS artifact
ORDER BY a.id
