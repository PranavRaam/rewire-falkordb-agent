"""Bounded model tool-calling loop over the typed Rewire MCP tool functions."""
from __future__ import annotations

import json
import os
import asyncio
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.client import Client
from rewire.mcp_server import mcp

ROOT = Path(__file__).resolve().parents[2]
MAX_TOOL_ROUNDS = 6
MAX_RESPONSE_BYTES = 1_500_000

TOOL_SCHEMAS = [
    {"type":"function","function":{"name":"inspect_run","description":"Read a run goal, state revision, selected plan and unresolved effects from FalkorDB.","strict":True,"parameters":{"type":"object","properties":{"graph_name":{"type":"string"},"run_id":{"type":"string"}},"required":["graph_name","run_id"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"discover_recovery","description":"Use FalkorDB-backed bounded AND/OR planning to discover conditional recovery steps. This never dispatches provider actions.","strict":True,"parameters":{"type":"object","properties":{"graph_name":{"type":"string"},"run_id":{"type":"string"},"now_ms":{"type":"integer"}},"required":["graph_name","run_id","now_ms"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"read_execution_evidence","description":"Read durable intent, attempt, receipt, event and output artifact evidence from FalkorDB.","strict":True,"parameters":{"type":"object","properties":{"graph_name":{"type":"string"},"run_id":{"type":"string"}},"required":["graph_name","run_id"],"additionalProperties":False}}},
]
TOOL_NAMES = {item["function"]["name"] for item in TOOL_SCHEMAS}


def _call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a selected model call through the registered MCP protocol tools."""
    async def call() -> dict[str, Any]:
        async with Client(mcp) as client:
            result = await client.call_tool(name, arguments)
            if result.is_error:
                raise RuntimeError(f"MCP tool {name} returned an error")
            structured = getattr(result, "structured_content", None)
            if structured is not None:
                return structured
            for item in result.content:
                value = getattr(item, "text", None)
                if value:
                    return json.loads(value)
            raise RuntimeError(f"MCP tool {name} returned no structured content")
    return asyncio.run(call())


def _verified_plan_summary(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build user-facing plan facts from tool results, never from model prose."""
    inspected = next((item.get("result") for item in trace
        if item.get("tool") == "inspect_run" and item.get("status") == "EXECUTED"), None)
    discovered = next((item.get("result") for item in reversed(trace)
        if item.get("tool") == "discover_recovery" and
        item.get("status") in ("EXECUTED", "POLICY_REQUIRED")), None)
    if not inspected or not discovered:
        return None
    steps = discovered.get("steps", [])
    rejected = discovered.get("rejected", [])
    query_ids = sorted({item.get("queryId") for item in discovered.get("queryEvidence", [])
                        if item.get("queryId")})
    facts = {
        "runStatus": inspected.get("runStatus"),
        "selectedPlanId": inspected.get("selectedPlanId") or None,
        "candidateStatus": discovered.get("status"),
        "steps": [{"toolId": step.get("toolId"), "status": step.get("status"),
                   "expectedOutputType": step.get("expectedOutputType")} for step in steps],
        "preservedArtifacts": discovered.get("preservedArtifacts", []),
        "rejected": [{"toolId": item.get("toolId"), "reasonCode": item.get("reasonCode"),
                      "observed": item.get("observed")} for item in rejected if item.get("toolId")],
        "queryIds": query_ids,
        "executionWarning": discovered.get("executionWarning"),
    }
    path = " → ".join(step["toolId"].removeprefix("tool:").removesuffix(":v1")
                     for step in facts["steps"])
    preserved = ", ".join(facts["preservedArtifacts"]) or "none"
    rejected_text = "; ".join(f"{item['toolId']} ({item['reasonCode']})" for item in facts["rejected"]) or "none"
    selection = facts["selectedPlanId"] or "no plan is selected yet"
    summary = (
        f"FalkorDB reports {facts['candidateStatus']} and {selection}. "
        f"It found a conditional {len(steps)}-step candidate: {path}. "
        f"Preserved: {preserved}. Rejected: {rejected_text}. "
        f"These steps are conditional, not executed. Evidence queries: {', '.join(query_ids)}."
    )
    return {"facts": facts, "summary": summary}


def _finish_verified_plan(trace: list[dict[str, Any]], *, provider: str, model: str,
                          draft: str, finish_reason: str | None, round_index: int) -> dict[str, Any]:
    verified = _verified_plan_summary(trace)
    if not verified:
        raise RuntimeError("required graph evidence is missing; refusing to complete a planning answer")
    return {"status":"COMPLETE","provider":provider,"model":model,
        "final":verified["summary"],"verifiedFacts":verified["facts"],
        "modelDraft":draft,"modelResponseStatus":"INCOMPLETE" if finish_reason == "length" else "COMPLETE",
        "modelFinishReason":finish_reason,"answerMode":"verified_graph_summary",
        "toolTrace":trace,"rounds":round_index,
        "createdAtUtc":datetime.now(timezone.utc).isoformat()}


def _completion(messages: list[dict[str, Any]], model: str, provider: str) -> dict[str, Any]:
    if provider == "ollama":
        default_url = "http://127.0.0.1:11434/v1/chat/completions"
        auth = os.getenv("REWIRE_LLM_API_KEY", "ollama").strip() or "ollama"
    elif provider == "openai":
        default_url = "https://api.openai.com/v1/chat/completions"
        auth = os.getenv("OPENAI_API_KEY", "").strip()
    else:
        raise RuntimeError("REWIRE_LLM_PROVIDER must be 'ollama' or 'openai'")
    base = os.getenv("REWIRE_LLM_BASE_URL", default_url).rstrip("/")
    request: dict[str, Any] = {"model":model,"messages":messages,"tools":TOOL_SCHEMAS,
        "temperature":0}
    if provider == "ollama":
        # Keep local inference tractable on modest GPUs; selected models can spill
        # layers to system RAM while using a bounded context and answer length.
        # Ollama's OpenAI-compatible endpoint uses reasoning_effort="none" to
        # disable hidden reasoning for tool-heavy latency-sensitive requests.
        request["options"] = {
            "num_ctx": int(os.getenv("REWIRE_LLM_CONTEXT", "4096")),
            "num_predict": int(os.getenv("REWIRE_LLM_MAX_TOKENS", "384")),
        }
        request["max_tokens"] = int(os.getenv("REWIRE_LLM_MAX_TOKENS", "384"))
        request["reasoning_effort"] = "none"
    else:
        request["tool_choice"] = "auto"
        request["parallel_tool_calls"] = False
    request["stream"] = False
    request_body = json.dumps(request).encode()
    req = urllib.request.Request(base, data=request_body, method="POST", headers={
        "Authorization":f"Bearer {auth}","Content-Type":"application/json"})
    timeout = max(10, int(os.getenv("REWIRE_LLM_TIMEOUT_SECONDS", "300")))
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("model response exceeded configured byte limit")
        return json.loads(raw)


def run_agent(user_request: str, graph_name: str, run_id: str, now_ms: int,
              *, max_tool_rounds: int = MAX_TOOL_ROUNDS) -> dict[str, Any]:
    """Ask a configured model to inspect and reason with bounded read-only tools."""
    provider = os.getenv("REWIRE_LLM_PROVIDER", "ollama").strip().lower()
    model = os.getenv("REWIRE_LLM_MODEL", "qwen3.5:4b" if provider == "ollama" else "").strip()
    if provider == "openai" and not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY is not set; remote model execution is unavailable")
    if not model:
        raise RuntimeError("REWIRE_LLM_MODEL is not set; choose a model enabled for your API account")
    messages: list[dict[str, Any]] = [
        {"role":"system","content":("You are Rewire, a connected-data workflow recovery agent. "
            "Use inspect_run before making claims. For any request about plans, recovery, candidates, feasibility, "
            "or available actions, you MUST use discover_recovery after inspect_run. An empty selectedPlanId means "
            "no plan has been selected; it does not mean no candidate plan exists. "
            "Treat planner output as conditional. Never claim a provider action happened unless read_execution_evidence "
            "returns a confirmed receipt. Never invent missing graph evidence. The available tools are read-only. "
            "After gathering evidence, answer in at most 100 words. State the feasible conditional path, preserved "
            "artifacts, rejected tool IDs with exact reason codes, and cite the query IDs supporting those facts." )},
        {"role":"user","content":f"Graph: {graph_name}\nRun: {run_id}\nSynthetic world time ms: {now_ms}\nRequest: {user_request}"},
    ]
    trace: list[dict[str, Any]] = []
    for round_index in range(max_tool_rounds + 1):
        response = _completion(messages, model, provider)
        choices = response.get("choices") or []
        if not choices:
            raise RuntimeError("model returned no completion choices")
        message = choices[0].get("message", {})
        finish_reason = choices[0].get("finish_reason")
        calls = message.get("tool_calls") or []
        messages.append(message)
        if not calls:
            requested = user_request.casefold()
            discovery_needed = any(term in requested for term in (
                "plan", "recover", "recovery", "candidate", "feasible", "what can be done", "available action"
            ))
            discovery_done = any(item.get("tool") == "discover_recovery" and
                                 item.get("status") in ("EXECUTED", "POLICY_REQUIRED") for item in trace)
            if discovery_needed:
                inspected = any(item.get("tool") == "inspect_run" and item.get("status") == "EXECUTED"
                                for item in trace)
                if not inspected:
                    evidence = _call_mcp_tool("inspect_run", {"graph_name":graph_name,"run_id":run_id})
                    trace.append({"round":round_index,"tool":"inspect_run",
                        "arguments":{"graph_name":graph_name,"run_id":run_id},
                        "status":"POLICY_REQUIRED","result":evidence})
                if not discovery_done:
                    evidence = _call_mcp_tool("discover_recovery", {
                        "graph_name":graph_name,"run_id":run_id,"now_ms":now_ms})
                    trace.append({"round":round_index,"tool":"discover_recovery",
                        "arguments":{"graph_name":graph_name,"run_id":run_id,"now_ms":now_ms},
                        "status":"POLICY_REQUIRED","result":evidence})
                result = _finish_verified_plan(trace, provider=provider, model=model,
                    draft=message.get("content") or "", finish_reason=finish_reason, round_index=round_index)
                _save_trace(result)
                return result
            answer_status = "INCOMPLETE" if finish_reason == "length" else "COMPLETE"
            verified = _verified_plan_summary(trace)
            result = {"status":"COMPLETE" if verified else answer_status,
                "provider":provider,"model":model,
                "final":verified["summary"] if verified else (message.get("content") or ""),
                "verifiedFacts":verified["facts"] if verified else None,
                "modelDraft":message.get("content") or "",
                "modelResponseStatus":answer_status,"modelFinishReason":finish_reason,
                "toolTrace":trace,"rounds":round_index,
                "createdAtUtc":datetime.now(timezone.utc).isoformat()}
            _save_trace(result)
            return result
        if round_index >= max_tool_rounds:
            trace.append({"round":round_index,"status":"REJECTED","reason":"MAX_TOOL_ROUNDS"})
            break
        for call in calls:
            call_id = call.get("id", "")
            function = call.get("function") or {}
            name = function.get("name", "")
            try:
                args = json.loads(function.get("arguments", "{}"))
                if name not in TOOL_NAMES or not isinstance(args, dict):
                    raise ValueError("tool name or arguments are invalid")
                if args.get("graph_name") != graph_name or args.get("run_id") != run_id:
                    raise ValueError("model tool call attempted to change graph/run scope")
                output = _call_mcp_tool(name, args)
                trace.append({"round":round_index,"tool":name,"arguments":args,"status":"EXECUTED","result":output})
                content = json.dumps(output, sort_keys=True)
            except Exception as exc:
                trace.append({"round":round_index,"tool":name,"argumentsRaw":function.get("arguments"),
                    "status":"INVALID_OR_FAILED","errorType":type(exc).__name__,"error":str(exc)})
                content = json.dumps({"error":"TOOL_CALL_REJECTED","message":str(exc)})
            messages.append({"role":"tool","tool_call_id":call_id,"content":content})
        requested = user_request.casefold()
        discovery_needed = any(term in requested for term in (
            "plan", "recover", "recovery", "candidate", "feasible", "what can be done", "available action"
        ))
        if discovery_needed:
            inspected = any(item.get("tool") == "inspect_run" and item.get("status") == "EXECUTED"
                            for item in trace)
            if not inspected:
                evidence = _call_mcp_tool("inspect_run", {"graph_name":graph_name,"run_id":run_id})
                trace.append({"round":round_index,"tool":"inspect_run",
                    "arguments":{"graph_name":graph_name,"run_id":run_id},
                    "status":"POLICY_REQUIRED","result":evidence})
            discovered = any(item.get("tool") == "discover_recovery" and
                item.get("status") in ("EXECUTED", "POLICY_REQUIRED") for item in trace)
            if not discovered:
                evidence = _call_mcp_tool("discover_recovery", {
                    "graph_name":graph_name,"run_id":run_id,"now_ms":now_ms})
                trace.append({"round":round_index,"tool":"discover_recovery",
                    "arguments":{"graph_name":graph_name,"run_id":run_id,"now_ms":now_ms},
                    "status":"POLICY_REQUIRED","result":evidence})
            verified_result = _finish_verified_plan(trace, provider=provider, model=model,
                draft=message.get("content") or "", finish_reason=finish_reason,
                round_index=round_index + 1)
            _save_trace(verified_result)
            return verified_result
    result = {"status":"BOUNDED_STOP","provider":provider,"model":model,"final":"The agent stopped at its configured tool-call limit.",
        "toolTrace":trace,"rounds":max_tool_rounds,"createdAtUtc":datetime.now(timezone.utc).isoformat()}
    _save_trace(result)
    return result


def _save_trace(result: dict[str, Any]) -> None:
    token = uuid.uuid4().hex[:10]
    path = ROOT / "reports" / "phase-04" / "runs" / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{token}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    result["tracePath"] = str(path)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Run Rewire with a configured model")
    parser.add_argument("--graph", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--now-ms", required=True, type=int)
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run_agent(args.request,args.graph,args.run,args.now_ms),indent=2))
    except (RuntimeError, urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"Agent run failed: {type(exc).__name__}: {exc}") from exc


if __name__ == "__main__":
    main()
