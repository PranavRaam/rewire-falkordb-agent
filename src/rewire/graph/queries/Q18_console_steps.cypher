MATCH (r:Run {id: $runId})-[:HAS_PLAN]->(p:Plan)-[:HAS_STEP]->(s:PlanStep)
WHERE r.selectedPlanId = p.id
MATCH (s)-[:USES_TOOL]->(t:ToolRevision)
OPTIONAL MATCH (i:Intent)-[:FOR_STEP]->(s)
OPTIONAL MATCH (receipt:Receipt)-[:CONFIRMS]->(i)
RETURN s.ordinal AS ordinal, s.status AS status, t.id AS toolId,
       i.status AS intentStatus, i.operationKey AS operationKey,
       receipt.id AS receiptId, receipt.providerRecordId AS providerRecordId
ORDER BY ordinal
