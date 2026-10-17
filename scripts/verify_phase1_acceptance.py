"""Run the six Phase 1 acceptance probes against isolated FalkorDB graphs."""
from __future__ import annotations
import json
import os
from dataclasses import replace
from pathlib import Path
import socket
import tempfile
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))
from rewire.domain import Goal
from rewire.fixtures import base_scenario
from rewire.graph.store import GraphStore, load_query, result_rows, validate_scenario
from rewire.planner.engine import ConditionalPlanner, MAX_DEPTH, MAX_EXPANSIONS
import rewire.graph.store as graph_store_module


def new_graph(store, scenario=None):
    suffix = uuid.uuid4().hex[:12]
    name, run = f"rewire_phase1_accept_{suffix}", f"run-accept-{suffix}"
    if scenario is None:
        scenario = replace(base_scenario(), run_id=run)
    else:
        scenario = replace(scenario, run_id=run)
    store.install_schema(name)
    store.seed(name, scenario)
    return name, run, scenario


def add_tool(graph, *, tool_id, output, slot_type=None, slot_id=None):
    schema = f"{output.lower()}-v1"
    graph.query("MERGE (ty:ArtifactType {id:$output}) ON CREATE SET ty.schemaVersion=$schema "
        "CREATE (t:ToolRevision {id:$id,toolId:$publicId,version:1,catalogRevision:1,enabled:true,"
        "adapterId:$adapter,effectClass:'READ_ONLY',maxWeightKg:0,outputBindingsJson:'{}'}) "
        "CREATE (t)-[:PRODUCES]->(ty) RETURN t.id",
        {"output":output,"schema":schema,"id":f"tool:{tool_id}:v1","publicId":tool_id,
         "adapter":f"adapter:{tool_id}"})
    if slot_type:
        graph.query("MERGE (ty:ArtifactType {id:$typeId}) ON CREATE SET ty.schemaVersion=$schema "
            "CREATE (s:RequirementSlot {id:$slotId,name:'input',cardinality:1,schemaVersion:$schema,"
            "minVersion:1,requiredStatus:'*',scopeOrder:false,scopeWarehouse:false,ruleId:'synthetic',"
            "outputBindingsJson:'{}'}) WITH s,ty MATCH (t:ToolRevision {id:$toolId}) "
            "CREATE (t)-[:REQUIRES]->(s) CREATE (s)-[:OF_TYPE]->(ty) RETURN s.id",
            {"typeId":slot_type,"schema":f"{slot_type.lower()}-v1","slotId":slot_id or f"slot:{tool_id}:input",
             "toolId":f"tool:{tool_id}:v1"})


def renamed_scenario(base, token, reverse=False):
    mapping = {}
    def rename(value):
        if value not in mapping:
            mapping[value] = f"renamed:{token}:{value}"
        return mapping[value]
    goal = replace(base.goal, id=rename(base.goal.id), output_type=rename(base.goal.output_type),
        order_id=rename(base.goal.order_id), warehouse_id=rename(base.goal.warehouse_id))
    artifacts = tuple(replace(a,id=rename(a.id),type_id=rename(a.type_id),order_id=rename(a.order_id),
        warehouse_id=rename(a.warehouse_id),properties={k:rename(v) if k.endswith("Id") and isinstance(v,str) else v
            for k,v in a.properties.items()}) for a in base.artifacts)
    tools = []
    for tool in base.tools:
        new_id, public_id, output = rename(tool.id), rename(tool.tool_id), rename(tool.output_type)
        slots = tuple(replace(slot,id=rename(slot.id),type_id=rename(slot.type_id),
            rule_id=rename(slot.rule_id)) for slot in tool.slots)
        tools.append(replace(tool,id=new_id,tool_id=public_id,adapter_id=rename(tool.adapter_id),
            output_type=output,slots=slots,consumes=tuple(rename(x) for x in tool.consumes)))
    if reverse:
        artifacts, tools = tuple(reversed(artifacts)), tuple(reversed(tools))
    return replace(base,name=f"renamed-{token}",goal=goal,artifacts=artifacts,tools=tuple(tools))


def importer_probes():
    scenario = base_scenario()
    checks = {}
    bad_artifact = replace(scenario.artifacts[0],schema_version="conflicting-v99")
    try:
        validate_scenario(replace(scenario,artifacts=(bad_artifact,*scenario.artifacts[1:])))
    except ValueError as exc:
        checks["conflictingArtifactTypeSchemaRejectedBeforeWrite"] = "ArtifactType" in str(exc) or "schema" in str(exc).lower()
    else: raise AssertionError("conflicting ArtifactType schema accepted")
    bad_tools = list(scenario.tools)
    slot = replace(bad_tools[-1].slots[0],cardinality=2)
    bad_tools[-1] = replace(bad_tools[-1],slots=(slot,))
    try: validate_scenario(replace(scenario,tools=tuple(bad_tools)))
    except ValueError as exc: checks["unsupportedSlotCardinalityRejected"] = "exactly-one" in str(exc)
    else: raise AssertionError("unsupported cardinality accepted")
    original = graph_store_module.relationship_rows
    def missing_endpoint(*args, **kwargs):
        rows = list(original(*args, **kwargs)); rel = rows[0]
        rows[0] = (rel[0], "missing:source", rel[2], rel[3]); return rows
    with patch.object(graph_store_module,"relationship_rows",missing_endpoint):
        try: validate_scenario(scenario)
        except ValueError as exc: checks["corruptRelationshipEndpointRejected"] = "Missing" in str(exc)
        else: raise AssertionError("corrupt relationship endpoint accepted")
    def duplicate_edge(*args, **kwargs):
        rows=list(original(*args,**kwargs)); rows.append(rows[0]); return rows
    with patch.object(graph_store_module,"relationship_rows",duplicate_edge):
        try: validate_scenario(scenario)
        except ValueError as exc: checks["duplicateRelationshipRejected"] = "Duplicate relationship" in str(exc)
        else: raise AssertionError("duplicate relationship accepted")
    assert all(checks.values()), checks
    return checks


def main():
    store = GraphStore()
    report = {"status":"RUNNING","checks":{}}
    try:
        # 1. Cycle and depth/search-bound behavior, plus a complete large query result.
        graph_name, run_id, scenario = new_graph(store)
        graph = store.select(graph_name)
        graph.query("MATCH (t:ToolRevision)-[:PRODUCES]->(ty:ArtifactType {id:'Booking'}) SET t.enabled=false")
        add_tool(graph,tool_id="cycle-root",output="CycleRoot",slot_type="CycleA")
        add_tool(graph,tool_id="cycle-a",output="CycleA",slot_type="CycleB")
        add_tool(graph,tool_id="cycle-b",output="CycleB",slot_type="CycleA")
        cycle = ConditionalPlanner(store,graph_name,run_id,replace(scenario.goal,output_type="CycleRoot"),
            scenario.now_ms,1).discover()
        assert cycle["status"]=="EXHAUSTIVE_NO_PLAN" and any(x.get("reasonCode")=="DEPENDENCY_CYCLE" for x in cycle["blockers"]),cycle
        report["checks"]["dependencyCycleTerminatesAsExhaustiveNoPlan"]=True
        for i in range(MAX_DEPTH+3):
            add_tool(graph,tool_id=f"depth-{i:02}",output=f"Depth{i}",
                slot_type=f"Depth{i+1}" if i<MAX_DEPTH+2 else None)
        depth = ConditionalPlanner(store,graph_name,run_id,replace(scenario.goal,output_type="Depth0"),
            scenario.now_ms,1).discover()
        assert depth["status"]=="SEARCH_LIMIT_REACHED" and depth["exploredExpansions"]>=MAX_DEPTH+1,depth
        report["checks"]["depthBoundIsReportedSeparatelyFromExhaustiveFailure"]=True
        scale=MAX_EXPANSIONS+20
        rows=[{"id":f"stress-tool-{i:05}","toolId":f"stress-{i:05}","version":1,
            "catalogRevision":1,"enabled":True,"adapterId":"adapter:stress","effectClass":"READ_ONLY",
            "maxWeightKg":0,"outputBindingsJson":"{}"} for i in range(scale)]
        graph.query("CREATE (:ArtifactType {id:'StressOutput',schemaVersion:'stress-v1'})")
        graph.query("UNWIND $rows AS row CREATE (t:ToolRevision {id:row.id,toolId:row.toolId,version:row.version,"
            "catalogRevision:row.catalogRevision,enabled:row.enabled,adapterId:row.adapterId,effectClass:row.effectClass,"
            "maxWeightKg:row.maxWeightKg,outputBindingsJson:row.outputBindingsJson}) "
            "WITH t MATCH (out:ArtifactType {id:'StressOutput'}) CREATE (t)-[:PRODUCES]->(out)",{"rows":rows})
        raw=result_rows(graph.ro_query(load_query("Q01_producers"),{"typeId":"StressOutput","catalogRevision":1,"weightKg":1}))
        assert len(raw)==scale,(len(raw),scale)
        limited=ConditionalPlanner(store,graph_name,run_id,replace(scenario.goal,output_type="Depth0"),
            scenario.now_ms,1,max_expansions=2).discover()
        assert limited["status"]=="SEARCH_LIMIT_REACHED" and limited["exploredExpansions"]==3,limited["status"]
        report["checks"]["largeProducerQueryReturnsAllRows"]={"rows":len(raw),"expected":scale}
        report["checks"]["plannerSearchLimitIsExplicit"]={"plannerStatus":limited["status"],
            "expansions":limited["exploredExpansions"],"testBound":2,"productionBound":MAX_EXPANSIONS}

        # 2 and 4. Identical IDs in distinct graphs do not cross-read; renamed and
        # permuted fixtures preserve the selected plan's semantic shape.
        isolated_scenario=base_scenario()
        g1,r1,_=new_graph(store,isolated_scenario)
        changed=replace(isolated_scenario,artifacts=tuple(replace(a,status="RELEASED") if a.id=="artifact:reservation:R81" else a
            for a in isolated_scenario.artifacts))
        g2,r2,_=new_graph(store,changed)
        q="MATCH (r:Run {id:$runId})-[:HAS_ARTIFACT]->(a:Artifact {id:'artifact:reservation:R81'}) RETURN a.status AS status"
        one=result_rows(store.select(g1).ro_query(q,{"runId":r1})); two=result_rows(store.select(g2).ro_query(q,{"runId":r2}))
        assert one==[{"status":"HELD"}] and two==[{"status":"RELEASED"}],(one,two)
        report["checks"]["sameIdsAreIsolatedByGraphName"]=True
        renamed=renamed_scenario(base_scenario(),"x",False)
        permuted=renamed_scenario(base_scenario(),"x",True)
        gr1,rr1,sc1=new_graph(store,renamed); gr2,rr2,sc2=new_graph(store,permuted)
        def plan(g,r,s):
            return ConditionalPlanner(store,g,r,s.goal,s.now_ms,1).discover()
        p1,p2=plan(gr1,rr1,sc1),plan(gr2,rr2,sc2)
        shape=lambda p:[(step["ordinal"],len(step["inputs"]),step["expectedOutputType"].split(":")[-1]) for step in p["steps"]]
        assert p1["status"]==p2["status"]=="STRUCTURALLY_VALID" and shape(p1)==shape(p2),(shape(p1),shape(p2))
        report["checks"]["renamedIdsAndPermutedImportPreservePlanShape"]=True

        # 3. Prove connection failure fails closed without an in-memory planner.
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0)); closed_port=sock.getsockname()[1]
        sock.close()
        outage={"failedClosed":False,"errorType":None}
        with patch.dict(os.environ,{"REWIRE_FALKOR_PORT":str(closed_port)}):
            try: GraphStore()
            except Exception as exc: outage={"failedClosed":True,"errorType":type(exc).__name__}
        assert outage["failedClosed"],outage
        report["checks"]["databaseOutageFailsClosedWithoutMemoryFallback"]=outage

        # 5. Malformed importer contracts are rejected before GraphStore.seed writes.
        report["checks"].update(importer_probes())
        report["status"]="PASS"
    finally:
        store.close()
    target=ROOT/"reports"/"phase-01"/"acceptance-verification.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__": main()
