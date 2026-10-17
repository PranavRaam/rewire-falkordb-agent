MATCH (r:Run {id: $runId})-[:EMITTED]->(e:Event)
RETURN e.sequence AS sequence, e.type AS type, e.timestamp AS timestamp
ORDER BY sequence
