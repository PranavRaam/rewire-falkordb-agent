MATCH (p:Plan {id: $planId})-[:HAS_STEP]->(changed:PlanStep {id: $stepId})
MATCH (p)-[:HAS_STEP]->(dependent:PlanStep)
MATCH (dependent)-[:DEPENDS_ON*1..12]->(changed)
RETURN DISTINCT dependent.id AS stepId, dependent.status AS status
