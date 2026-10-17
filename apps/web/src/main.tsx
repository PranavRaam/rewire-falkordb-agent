import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Braces,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Clock3,
  Database,
  FileCheck2,
  GitBranch,
  Layers3,
  LoaderCircle,
  Network,
  Package,
  Play,
  Plus,
  ShieldCheck,
  Square,
  Terminal,
  TriangleAlert,
  X,
} from "lucide-react";
import "@xyflow/react/dist/style.css";
import "@fontsource-variable/manrope";
import "@fontsource/ibm-plex-mono/400.css";
import "./style.css";
import { Workflow } from "./Workflow";
import { Dialog, ReceiptList } from "./components";
import {
  api,
  pretty,
  toolTitle,
  eventTitle,
  type Run,
  type Health,
  type Audit,
  type RunSummary,
} from "./types";

const phases = [
  "Understand the break",
  "Find a way forward",
  "Approve the repair",
  "Prove the outcome",
];
function App() {
  const [narrow, setNarrow] = useState(
    () => window.matchMedia("(max-width:760px)").matches,
  );
  const [health, setHealth] = useState<Health | null>(null),
    [run, setRun] = useState<Run | null>(null),
    [history, setHistory] = useState<RunSummary[]>([]);
  const [view, setView] = useState("overview"),
    [tab, setTab] = useState("decision"),
    [selected, setSelected] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"new" | "approval" | null>(
      null,
    ),
    [fault, setFault] = useState(true),
    [mode, setMode] = useState<"model" | "direct">("model");
  const [error, setError] = useState(""),
    [working, setWorking] = useState(false),
    [connected, setConnected] = useState(false),
    [audit, setAudit] = useState<Audit | null>(null);
  const [replay, setReplay] = useState<number | null>(null),
    [playing, setPlaying] = useState(false),
    [list, setList] = useState(false),
    [queryIndex, setQueryIndex] = useState(0);
  const refreshHistory = () =>
    api<RunSummary[]>("/runs")
      .then(setHistory)
      .catch(() => {});
  useEffect(() => {
    const media = window.matchMedia("(max-width:760px)");
    const update = () => {
      setNarrow(media.matches);
      setList(media.matches);
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    refreshHistory();
    const refresh = () =>
      api<Health>("/health")
        .then(setHealth)
        .catch(() => setHealth(null));
    refresh();
    const id = setInterval(refresh, 15000);
    const saved = localStorage.getItem("rewire-run");
    if (saved)
      api<Run>("/runs/" + saved)
        .then(setRun)
        .catch(() => localStorage.removeItem("rewire-run"));
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (!run?.runId) return;
    setConnected(false);
    setAudit(null);
    localStorage.setItem("rewire-run", run.runId);
    const source = new EventSource("/api/runs/" + run.runId + "/events");
    source.addEventListener("snapshot", (event) => {
      setRun(JSON.parse((event as MessageEvent).data));
      setConnected(true);
    });
    source.addEventListener("unavailable", () => setConnected(false));
    source.onerror = () => setConnected(false);
    return () => source.close();
  }, [run?.runId]);
  useEffect(() => {
    if (!playing || !run) return;
    const id = setInterval(
      () =>
        setReplay((value) => {
          const next = (value ?? 0) + 1;
          if (next >= run.events.length) {
            setPlaying(false);
            return run.events.length;
          }
          return next;
        }),
      800,
    );
    return () => clearInterval(id);
  }, [playing, run?.events.length]);
  const complete = run?.state.runStatus === "SUCCEEDED";
  const valid = run?.plan?.status === "STRUCTURALLY_VALID";
  const observedEvents = run
    ? replay === null
      ? run.events
      : run.events.slice(0, replay)
    : [];
  const seenComplete =
    replay === null
      ? complete
      : observedEvents.some((e) => e.type === "run.succeeded");
  const unknown =
    (observedEvents.filter((e) => e.type === "effect.unknown").at(-1)
      ?.sequence || 0) >
    (observedEvents.filter((e) => e.type === "effect.confirmed").at(-1)
      ?.sequence || 0);
  const status = !run
    ? "Ready to begin"
    : replay !== null
      ? "Recorded replay"
      : unknown
        ? "Outcome unknown"
        : complete
          ? "Shipment confirmed"
          : run.busy
            ? "Recovery in progress"
            : !valid
              ? "Recovery blocked"
              : run.interrupted
                ? "Session interrupted"
                : "Ready for approval";
  const carrier = run?.plan?.steps[0]?.adapterId.includes("carrier-d")
    ? "D"
    : "B";
  const receiptCount =
    replay === null
      ? run?.executionSteps.filter((s) => s.receiptId).length || 0
      : observedEvents.filter((e) => e.type === "effect.confirmed").length;
  const eventCount = observedEvents.length;
  const approved = observedEvents.some((e) => e.type === "plan.approved");
  const quote = seenComplete
    ? run?.artifacts.find((a) => a.priceUnits !== undefined)
    : undefined;
  const booking = seenComplete
    ? run?.artifacts.find((a) => a.bookingId)
    : undefined;
  const step = run?.plan?.steps.find((s) => s.id === selected);
  const artifact = run?.artifacts.find((a) => a.id === selected);
  const rejection = run?.plan?.rejected.find((r) => r.toolId === selected);
  const queries = run?.plan?.evidence || [];
  const selectRecord = React.useCallback((id: string) => {
    setSelected(id);
    setTab("decision");
  }, []);
  async function createRun() {
    setWorking(true);
    setError("");
    try {
      const value = await api<Run>("/runs", {
        scenario: "base",
        faultAfterCommit: fault,
      });
      setRun(value);
      setDialog(null);
      setReplay(null);
      setSelected(null);
      setView("workspace");
      refreshHistory();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  async function execute() {
    if (!run) return;
    setWorking(true);
    setError("");
    try {
      await api("/runs/" + run.runId + "/execute", {
        approvalDigest: run.approvalDigest,
        mode,
      });
      setRun({ ...run, busy: true });
      setDialog(null);
      refreshHistory();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  async function readAudit() {
    if (!run) return;
    setWorking(true);
    try {
      setAudit(await api<Audit>("/runs/" + run.runId + "/audit"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  async function openRun(id: string) {
    setError("");
    try {
      setRun(await api<Run>("/runs/" + id));
      setReplay(null);
      setPlaying(false);
      setSelected(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function startReplay() {
    setReplay(0);
    setPlaying(true);
    setView("workspace");
  }
  function mainAction() {
    if (!run) setDialog("new");
    else if (complete) {
      setView("evidence");
      setTab("receipts");
    } else if (valid) setDialog("approval");
    else setDialog("new");
  }
  function startRecoveryCase() {
    setFault(true);
    setView("workspace");
    setDialog("new");
  }
  const overview = (
    <div className="operations-dashboard">
      <header className="ops-heading">
        <div>
          <div className="ops-eyebrow">OPERATIONS / RECOVERY</div>
          <h1>Workflow recovery</h1>
          <p>Inspect a connected-data plan, authorize its actions, and verify the provider outcome.</p>
        </div>
        <button className="primary" onClick={startRecoveryCase} disabled={!!run?.busy}>
          <Plus size={16} /> New recovery
        </button>
      </header>

      <section className="service-strip" aria-label="Service status">
        <div><span className={`service-light ${health?.graph ? "up" : "down"}`} /><span>FalkorDB</span><strong>{health?.graph ? "Connected" : "Unavailable"}</strong></div>
        <div><span className={`service-light ${health?.modelAvailable ? "up" : "down"}`} /><span>Agent model</span><strong>{health?.modelAvailable ? health.model : "Unavailable"}</strong></div>
        <div><span className="service-light up" /><span>Provider</span><strong>Local simulator</strong></div>
        <div className="service-context">All records in this workspace are synthetic.</div>
      </section>

      <section className="case-workspace">
        <article className="case-card">
          <div className="case-card-head">
            <div><span className="case-label">DEMO FIXTURE · FULFILLMENT</span><span className="case-id">CASE RW-104</span></div>
            <span className={`case-state ${complete ? "complete" : run ? "active" : "ready"}`}>
              {run ? status : "Ready to run"}
            </span>
          </div>
          <h2>Shipment confirmation missing</h2>
          <p className="case-summary">Carrier A is unavailable. The booking request to Carrier B may have committed, but its response was lost. A blind retry could create a duplicate shipment.</p>
          <div className="case-facts">
            <div><span>Order</span><strong>O-104 · replacement motor</strong></div>
            <div><span>Package</span><strong>8 kg · destination Z3</strong></div>
            <div><span>Inventory</span><strong>R81 · held reservation</strong></div>
            <div><span>Guardrails</span><strong>≤ 900 units · 16:00 IST</strong></div>
          </div>
          <div className="case-card-actions">
            <button className="primary" onClick={() => run ? setView("workspace") : startRecoveryCase()} disabled={!!run?.busy}>
              {run ? "Open recovery run" : "Analyze recovery"}<ArrowRight size={16} />
            </button>
            {run && <span>{run.runId} · {receiptCount} receipts recorded</span>}
          </div>
        </article>

        <aside className="case-decision">
          <div className="case-decision-title"><ShieldCheck size={18} /><span>SAFE ACTION POLICY</span></div>
          <h3>Check before retrying</h3>
          <p>Before another booking request, query the provider using the original operation key. If the provider committed, record its receipt and stop.</p>
          <div className="decision-rule"><span>Expected recovery</span><strong>Reconcile → verify → finish</strong></div>
          <div className="decision-rule"><span>Blocked shortcut</span><strong>Retry with a new key</strong></div>
        </aside>
      </section>

      <section className="graph-workbench">
        <header>
          <div><div className="ops-eyebrow">GRAPH EXECUTION PATH</div><h2>What FalkorDB contributes</h2></div>
          <button className="text-button" onClick={() => { setView("evidence"); setTab("queries"); }} disabled={!run}>
            Open Cypher trace <ArrowUpRight size={15} />
          </button>
        </header>
        <div className="graph-stages">
          <article><span>01 · DISCOVER</span><strong>Candidate tools</strong><p><code>Q01_producers</code> finds tool contracts that can produce the missing Booking.</p></article>
          <article><span>02 · BIND</span><strong>Compatible inputs</strong><p><code>Q02_bindings / Q03_exact_binding</code> check artifact type, scope, version and readiness.</p></article>
          <article><span>03 · ACT</span><strong>Approved recovery</strong><p>The bounded planner composes the returned graph facts. Provider mutations wait for approval.</p></article>
          <article><span>04 · VERIFY</span><strong>Recorded outcome</strong><p>FalkorDB records intents, receipts and events; the separate provider ledger is independently audited.</p></article>
        </div>
      </section>

      {history.length > 0 && (
        <section className="recent-operations">
          <header><div><div className="ops-eyebrow">LOCAL RUN HISTORY</div><h2>Recent recoveries</h2></div><button className="text-button" onClick={() => setView("workspace")}>Open current run <ArrowRight size={14} /></button></header>
          {history.slice(0, 4).map((entry) => (
            <button key={entry.runId} onClick={() => { void openRun(entry.runId); setView("workspace"); }}>
              <span className="run-ring" />
              <strong>{entry.runId}</strong>
              <span>{entry.scenario === "carrier-d" ? "Carrier D catalog change" : entry.scenario === "expired" ? "Expired reservation" : "Lost booking response"}</span>
              <small>{entry.jobStatus}</small><ChevronRight size={15} />
            </button>
          ))}
        </section>
      )}
    </div>
  );
  const content = (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            {view === "workspace"
              ? "OPERATIONS / RECOVERY RUN"
              : view === "evidence"
                ? "OPERATIONS / GRAPH & AUDIT"
                : "OPERATIONS / OVERVIEW"}
          </div>
          <h1>
            {view === "workspace"
              ? "Recovery run"
              : view === "evidence"
                ? "Graph & audit"
                : "Workflow recovery"}
          </h1>
          <p>
            {view === "workspace"
              ? run
                ? `Order ${run.state.goal.orderId} · ${run.plan.steps.length} proposed steps · ${receiptCount} provider receipts`
                : "Create an incident case to discover a recovery plan from the connected tool graph."
              : view === "evidence"
                ? "Review the Cypher queries, graph records, event history and provider audit for this run."
                : "Review the incident fixture, service status and FalkorDB decision path."}
          </p>
        </div>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          <TriangleAlert size={18} />
          <span>{error}</span>
          <button aria-label="Dismiss error" onClick={() => setError("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {run?.error && (
        <div className="error-banner" role="alert">
          <TriangleAlert size={18} />
          {run.error} Current graph evidence is preserved.
        </div>
      )}
      {run && !connected && (
        <div className="connection-banner" role="status">
          <LoaderCircle size={14} className="spin" /> Reconnecting to graph
          evidence. Execution controls are paused.
        </div>
      )}
      <>
          <section className="mission">
            <div className="mission-icon">
              <Package size={25} />
            </div>
            <div className="mission-main">
              <div className="mission-label">
                {run
                  ? `ORDER ${run.state.goal.orderId} / ${run.state.goal.warehouseId} → ${run.state.goal.destinationZone}`
                  : "SHIPMENT RECOVERY / LOCAL EXPERIMENT"}
              </div>
              <h2>
                {run
                  ? "One shipment. No duplicate booking."
                  : "The next move should be the right one."}
              </h2>
              <div className="constraints">
                {run ? (
                  <>
                    <span>{run.state.goal.weightKg} kg package</span>
                    <i />
                    <span>≤ {run.state.goal.maxCostUnits} cost units</span>
                    <i />
                    <span>
                      Before{" "}
                      {new Date(run.state.goal.cutoffAt).toLocaleTimeString(
                        "en-GB",
                        {
                          hour: "2-digit",
                          minute: "2-digit",
                          timeZone: "Asia/Kolkata",
                        },
                      )}{" "}
                      IST
                    </span>
                  </>
                ) : (
                  <span>A graph-directed agent for interrupted workflows</span>
                )}
              </div>
            </div>
            <div
              className={`status-pill ${seenComplete ? "success" : unknown ? "warning" : ""}`}
              role="status"
            >
              <span className="status-dot" />
              {status}
            </div>
          </section>
          <div className="stage-strip">
            {phases.map((title, i) => (
              <div
                key={title}
                className={`${run && (i < 2 || (i === 2 && approved) || (i === 3 && seenComplete)) ? "reached" : ""}`}
              >
                <span>
                  {run &&
                  (i < 2 ||
                    (i === 2 && approved) ||
                    (i === 3 && seenComplete)) ? (
                    <Check size={12} />
                  ) : (
                    String(i + 1).padStart(2, "0")
                  )}
                </span>
                {title}
                {i < 3 && <ChevronRight className="stage-arrow" size={15} />}
              </div>
            ))}
          </div>
          {view === "workspace" ? (
            <div className="workspace-grid">
              <section className="canvas-panel">
                <div className="panel-toolbar">
                  <div>
                    <GitBranch size={17} />
                    <strong>Execution plan</strong>
                    <span className="small-label">
                      {run ? `REV ${run.state.revision}` : "AWAITING RUN"}
                    </span>
                  </div>
                  <div className="segmented">
                    <button
                      className={!list ? "active" : ""}
                      onClick={() => setList(false)}
                    >
                      Graph
                    </button>
                    <button
                      className={list ? "active" : ""}
                      onClick={() => setList(true)}
                    >
                      Steps
                    </button>
                  </div>
                </div>
                <div className="canvas-caption">
                  <span className="tiny-dot" />{" "}
                  {replay !== null
                    ? "RECORDED EVIDENCE / NO ACTIONS"
                    : run
                      ? "FALKORDB / LIVE SYNTHETIC RUN"
                      : "FALKORDB / CONNECTED TOOL CONTRACTS"}
                  <span>
                    {run
                      ? `${run.plan.steps.length} planned steps`
                      : "Your graph is the source of truth"}
                  </span>
                </div>
                <div className="graph-area">
                  {run ? (
                    list ? (
                      <div className="step-list">
                        {run.plan.steps.map((s, i) => (
                          <button onClick={() => selectRecord(s.id)} key={s.id}>
                            <span
                              className={`step-index ${i < receiptCount ? "done" : ""}`}
                            >
                              {i < receiptCount ? <Check size={16} /> : i + 1}
                            </span>
                            <div>
                              <strong>{toolTitle(s.toolId)}</strong>
                              <small>
                                {s.inputs.length} required inputs →{" "}
                                {s.expectedOutputType}
                              </small>
                            </div>
                            <span className="tag">
                              {i < receiptCount ? "CONFIRMED" : "PROPOSED"}
                            </span>
                            <ChevronRight size={16} />
                          </button>
                        ))}
                        {!valid && (
                          <div className="empty-inline">
                            <TriangleAlert />
                            <h3>No valid recovery in this model</h3>
                            <p>
                              {run.plan.status === "SEARCH_LIMIT_REACHED"
                                ? "The search budget was reached. No exhaustive claim is made."
                                : "The planner exhausted this scenario. Inspect the missing or expired prerequisites."}
                            </p>
                          </div>
                        )}
                      </div>
                    ) : (
                      <Workflow
                        key={`${run.runId}-${narrow}`}
                        run={run}
                        selected={selected}
                        onSelect={selectRecord}
                        replayCount={replay}
                      />
                    )
                  ) : (
                    <div className="empty-canvas">
                      <div className="empty-network">
                        <div>
                          <Package size={24} />
                        </div>
                        <span />
                        <div className="empty-hub">
                          <GitBranch size={30} />
                        </div>
                        <span />
                        <div>
                          <ShieldCheck size={24} />
                        </div>
                      </div>
                      <span className="eyebrow">NO ACTIVE RECOVERY</span>
                      <h2>Analyze shipment O-104</h2>
                      <p>
                        Build a recovery plan from stored tool contracts and
                        the reservation state in FalkorDB.
                      </p>
                      <button
                        className="primary"
                        onClick={startRecoveryCase}
                      >
                        Analyze recovery <ArrowRight size={16} />
                      </button>
                    </div>
                  )}
                </div>
                <div className="canvas-footer">
                  <div className="legend">
                    <span>
                      <i className="existing" />
                      Existing input
                    </span>
                    <span>
                      <i className="proposed" />
                      Proposed action
                    </span>
                    <span>
                      <i className="confirmed" />
                      Confirmed
                    </span>
                  </div>
                  <span>Click any node to inspect</span>
                </div>
                {run && (
                  <div className="insight-bar">
                    <div className="insight-symbol">
                      <GitBranch size={18} />
                    </div>
                    <p>
                      <strong>
                        {!valid
                          ? "The safest action is to stop."
                          : seenComplete
                            ? "The repair is complete. The proof is below."
                            : "Carrier B is viable. Reservation R81 is preserved."}
                      </strong>
                      <br />
                      {!valid
                        ? "An unsatisfied prerequisite blocks execution. No provider action is authorized."
                        : `Carrier ${carrier} is selected from graph contracts. Existing inputs are reused; new outputs require provider confirmation.`}
                    </p>
                    <button
                      aria-label="Open query evidence"
                      onClick={() => setTab("queries")}
                    >
                      <ArrowUpRight size={18} />
                    </button>
                  </div>
                )}
              </section>
              <aside className="inspector">
                <div className="panel-toolbar">
                  <div>
                    <Layers3 size={17} />
                    <strong>Plan details</strong>
                  </div>
                  <span className="small-label">INSPECT</span>
                </div>
                <div className="inspector-tabs">
                  <button
                    className={tab === "decision" ? "active" : ""}
                    onClick={() => setTab("decision")}
                  >
                    Why this path
                  </button>
                  <button
                    className={tab === "queries" ? "active" : ""}
                    onClick={() => setTab("queries")}
                  >
                    Cypher queries
                  </button>
                  <button
                    className={tab === "receipts" ? "active" : ""}
                    onClick={() => setTab("receipts")}
                  >
                    Actions & audit
                  </button>
                </div>
                <div className="inspector-content">
                  {tab === "decision" ? (
                    <>
                      {!run ? (
                        <div className="empty-inspector">
                          <Network size={30} />
                          <h3>Plan details appear here.</h3>
                          <p>
                            After analysis, inspect the selected tool, graph
                            inputs, rejected options, and query records.
                          </p>
                          <div className="mini-rule">
                            <span>01</span> What is still valid?
                          </div>
                          <div className="mini-rule">
                            <span>02</span> What can produce the goal?
                          </div>
                          <div className="mini-rule">
                            <span>03</span> What proves it happened?
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="inspector-kicker">
                            {step
                              ? "SELECTED ACTION"
                              : artifact
                                ? "EXISTING ARTIFACT"
                                : rejection
                                  ? "REJECTED CANDIDATE"
                                  : "GRAPH-DERIVED PLAN"}
                          </div>
                          <h3>
                            {step
                              ? toolTitle(step.toolId)
                              : artifact
                                ? `${artifact.typeId} · ${artifact.reservationId || artifact.id.split(":").at(-1)}`
                                : rejection
                                  ? toolTitle(rejection.toolId!)
                                  : valid
                                    ? `Why Carrier ${carrier}?`
                                    : "Why execution is blocked"}
                          </h3>
                          <p className="explanation">
                            {step
                              ? `Produces ${step.expectedOutputType} after every required input passes current graph validation.`
                              : artifact
                                ? `Status ${artifact.status}, version ${artifact.version}. ${artifact.expiresAt ? `Expires at ${new Date(artifact.expiresAt).toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata" })} IST on the fixture clock.` : "No expiry recorded."}`
                                : rejection
                                  ? reason(rejection.reasonCode)
                                  : valid
                                    ? "Its prerequisites can be satisfied without replacing the existing reservation. Each input has a compatible type, scope and schema."
                                    : "The graph cannot satisfy every required input. Execution is disabled."}
                          </p>
                          {step ? (
                            <div className="binding-list">
                              <span className="section-label">
                                REQUIRED INPUTS · {step.inputs.length}
                              </span>
                              {step.inputs.map((b) => (
                                <div key={b.slotId}>
                                  <GitBranch size={14} />
                                  <div>
                                    <strong>{b.typeId}</strong>
                                    <small>
                                      {b.artifactId
                                        ? `Existing · ${b.artifactId.split(":").at(-1)}`
                                        : "Produced by an earlier step"}
                                    </small>
                                  </div>
                                  <span className="tag">
                                    {b.artifactId ? "BOUND" : "CONDITIONAL"}
                                  </span>
                                </div>
                              ))}
                            </div>
                          ) : artifact ? (
                            <pre className="record-json">
                              {pretty(artifact)}
                            </pre>
                          ) : (
                            <>
                              <div className="preserved-card">
                                <BookmarkIcon />
                                <div>
                                  <strong>
                                    {valid
                                      ? "R81 remains in the plan"
                                      : "R81 is not reusable"}
                                  </strong>
                                  <span>
                                    {valid
                                      ? "Existing reservation · reused input"
                                      : "Expired input · execution blocked"}
                                  </span>
                                </div>
                              </div>
                              <div className="section-title">
                                <span className="section-label">
                                  ALTERNATIVES CONSIDERED
                                </span>
                                <span className="small-label">GRAPH FACTS</span>
                              </div>
                              {run.plan.rejected
                                .filter(
                                  (r, i, a) =>
                                    r.toolId?.includes("dispatch") &&
                                    a.findIndex(
                                      (x) => x.toolId === r.toolId,
                                    ) === i,
                                )
                                .map((r) => (
                                  <button
                                    className="candidate"
                                    key={r.toolId}
                                    onClick={() => selectRecord(r.toolId!)}
                                  >
                                    <div className="candidate-icon">
                                      <X size={14} />
                                    </div>
                                    <div>
                                      <strong>
                                        {toolTitle(r.toolId!).replace(
                                          " Dispatch",
                                          "",
                                        )}
                                      </strong>
                                      <span>{reason(r.reasonCode)}</span>
                                    </div>
                                    <ChevronRight size={15} />
                                  </button>
                                ))}
                              {!valid &&
                                run.plan.blockers.slice(0, 3).map((b, i) => (
                                  <div className="candidate" key={i}>
                                    <TriangleAlert size={16} />
                                    <div>
                                      <strong>{b.typeId}</strong>
                                      <span>{reason(b.reasonCode)}</span>
                                    </div>
                                  </div>
                                ))}
                              <button
                                className="text-button evidence-link"
                                onClick={() => setTab("queries")}
                              >
                                Explore {queries.length} recorded queries{" "}
                                <ArrowUpRight size={14} />
                              </button>
                            </>
                          )}
                          <div className="guard-note">
                            <ShieldCheck size={16} />
                            <p>
                              {seenComplete
                                ? "Provider receipts establish the outcome. Use the independent audit to check the booking count."
                                : "A valid plan is conditional. The executor rechecks versions, ownership, expiry and the observed quote before proceeding."}
                            </p>
                          </div>
                        </>
                      )}
                    </>
                  ) : tab === "queries" ? (
                    <>
                      <div className="inspector-kicker">
                        EXACT DATABASE EVIDENCE
                      </div>
                      <h3>{queries.length} queries. Inspectable results.</h3>
                      <p className="explanation">
                        Recorded during discovery. Durations are measured
                        database round trips, not end-to-end agent time.
                      </p>
                      {queries.map((q, i) => (
                        <button
                          className="query-row"
                          key={i}
                          onClick={() => {
                            setQueryIndex(i);
                            setView("evidence");
                            setTab("queries");
                          }}
                        >
                          <span className="query-index">
                            {String(i + 1).padStart(2, "0")}
                          </span>
                          <div>
                            <strong>{q.queryId}</strong>
                            <span>
                              {q.rowCount} rows · {q.elapsedMs.toFixed(2)} ms
                            </span>
                          </div>
                          <ArrowUpRight size={14} />
                        </button>
                      ))}
                    </>
                  ) : (
                    <ReceiptList
                      run={run}
                      visibleCount={receiptCount}
                      onAudit={() => {
                        setView("evidence");
                        setTab("receipts");
                      }}
                    />
                  )}
                </div>
              </aside>
            </div>
          ) : (
            <section className="evidence-page">
              <div className="evidence-nav">
                <button
                  className={tab === "queries" ? "active" : ""}
                  onClick={() => setTab("queries")}
                >
                  <Braces size={16} /> Cypher queries
                </button>
                <button
                  className={tab === "receipts" ? "active" : ""}
                  onClick={() => setTab("receipts")}
                >
                  <FileCheck2 size={16} /> Actions & provider audit
                </button>
                <button
                  className={tab === "agent" ? "active" : ""}
                  onClick={() => setTab("agent")}
                >
                  <AudioLines size={16} /> Agent tool calls
                </button>
              </div>
              {!run ? (
                <div className="empty-inline">
                  <Database />
                  <h3>No run selected</h3>
                  <p>Analyze the shipment to inspect its graph queries and execution record.</p>
                </div>
              ) : tab === "queries" ? (
                <div className="query-explorer">
                  <div className="query-menu">
                    {queries.map((q, i) => (
                      <button
                        className={queryIndex === i ? "active" : ""}
                        key={i}
                        onClick={() => setQueryIndex(i)}
                      >
                        <span>{String(i + 1).padStart(2, "0")}</span>
                        <div>
                          <strong>{q.queryId}</strong>
                          <small>
                            {q.rowCount} rows · {q.elapsedMs.toFixed(2)} ms
                          </small>
                        </div>
                      </button>
                    ))}
                  </div>
                  <div className="query-detail">
                    {queries[queryIndex] && (
                      <>
                        <span className="eyebrow">
                          RECORDED DISCOVERY QUERY / {queryIndex + 1}
                        </span>
                        <h2>{queries[queryIndex].queryId}</h2>
                        <p>
                          Run {run.runId} · SHA-256{" "}
                          <code>
                            {queries[queryIndex].sha256.slice(0, 16)}…
                          </code>
                        </p>
                        <h4>Executed Cypher</h4>
                        <pre>{queries[queryIndex].query}</pre>
                        <h4>Bound parameters</h4>
                        <pre>{pretty(queries[queryIndex].params)}</pre>
                        <h4>
                          Returned records · {queries[queryIndex].rowCount}
                        </h4>
                        <pre>{pretty(queries[queryIndex].rows)}</pre>
                      </>
                    )}
                  </div>
                </div>
              ) : tab === "agent" ? (
                <div className="agent-evidence">
                  <span className="eyebrow">TOOL SELECTION THROUGH MCP</span>
                  <h2>
                    {run.executionMode === "model"
                      ? run.executionResult?.model || health?.model
                      : run.executionMode === "direct"
                        ? "Direct MCP execution"
                        : "Awaiting approved execution"}
                  </h2>
                  <p>
                    {run.executionMode === "direct"
                      ? "The operator selected the deterministic MCP path. No model inference is claimed."
                      : "The model selects typed tools. The host pins graph scope and supplies the operator’s exact approval."}
                  </p>
                  {run.busy && (
                    <div className="connection-banner">
                      <LoaderCircle className="spin" size={17} /> Local
                      inference is running. Confirmed provider evidence appears
                      as it arrives.
                    </div>
                  )}
                  {run.executionResult?.toolTrace?.map((item, i) => (
                    <details key={i} className="tool-record">
                      <summary>
                        <Terminal size={16} />
                        <strong>{item.tool}</strong>
                        <span className="tag">{item.status}</span>
                      </summary>
                      <pre>{pretty(item)}</pre>
                    </details>
                  ))}
                  {run.executionResult && (
                    <div className="guard-note">
                      <CheckCheck size={20} />
                      <p>
                        {run.executionResult.final ||
                          run.executionResult.status}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="audit-layout">
                  <div>
                    <ReceiptList run={run} visibleCount={receiptCount} />
                  </div>
                  <div className="audit-card">
                    <span className="eyebrow">INDEPENDENT EVALUATOR</span>
                    <h2>Trust, then check.</h2>
                    <p>
                      Read the provider’s separate SQLite ledger. This audit is
                      available to reviewers and is never passed to the
                      agent.
                    </p>
                    {audit ? (
                      <>
                        <div className="audit-count">
                          <strong>{audit.rowCounts.bookings}</strong>
                          <span>
                            committed booking
                            {audit.rowCounts.bookings === 1 ? "" : "s"}
                          </span>
                        </div>
                        <div className="audit-facts">
                          {Object.entries(audit.rowCounts)
                            .filter(([k]) => k !== "bookings")
                            .map(([k, v]) => (
                              <div key={k}>
                                <span>{k}</span>
                                <b>{v}</b>
                              </div>
                            ))}
                        </div>
                        <details>
                          <summary>Inspect provider ledger</summary>
                          <pre>{pretty(audit)}</pre>
                        </details>
                      </>
                    ) : (
                      <button
                        className="primary"
                        disabled={
                          !!run.busy || !run.executionSteps.length || working
                        }
                        onClick={readAudit}
                      >
                        <ShieldCheck size={16} /> Run independent audit
                      </button>
                    )}
                    <div className="guard-note">
                      <Database size={17} />
                      <p>
                        Separate storage, separate evidence. The graph stores
                        the agent’s observations; the ledger records provider
                        effects.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </section>
          )}
          {run && view === "workspace" && (
            <section className="timeline-panel">
              <div className="panel-toolbar">
                <div>
                  <Activity size={17} />
                  <strong>Execution journal</strong>
                  <span className="small-label">{eventCount} EVENTS</span>
                </div>
                <div>
                  {run.events.length > 0 && (
                    <button className="text-button" onClick={startReplay}>
                      <Play size={13} /> Replay evidence
                    </button>
                  )}
                  <span className="clock-label">
                    <Clock3 size={13} /> Frozen fixture clock ·{" "}
                    {new Date(run.nowMs).toLocaleTimeString("en-GB", {
                      timeZone: "Asia/Kolkata",
                    })}{" "}
                    IST
                  </span>
                </div>
              </div>
              {replay !== null && (
                <div className="replay-controls">
                  <span
                    className="replay-label"
                    title="The journal drives step playback. Artifact details and query evidence show the saved final snapshot."
                  >
                    RECORDED REPLAY
                  </span>
                  <button
                    className="icon-button"
                    aria-label={playing ? "Pause replay" : "Play replay"}
                    onClick={() => setPlaying(!playing)}
                  >
                    {playing ? <Square size={13} /> : <Play size={13} />}
                  </button>
                  <input
                    aria-label="Recorded event position"
                    type="range"
                    min={0}
                    max={run.events.length}
                    value={replay}
                    onChange={(e) => {
                      setPlaying(false);
                      setReplay(+e.target.value);
                    }}
                  />
                  <span>
                    {replay}/{run.events.length}
                  </span>
                  <button
                    className="text-button"
                    onClick={() => {
                      setReplay(null);
                      setPlaying(false);
                    }}
                  >
                    Return to live
                  </button>
                </div>
              )}
              <div className="journal">
                {observedEvents.length ? (
                  observedEvents.map((e) => (
                    <div
                      className={`journal-event ${e.type === "effect.unknown" ? "unknown-event" : ""}`}
                      key={e.sequence}
                    >
                      <span className="journal-seq">
                        {String(e.sequence).padStart(2, "0")}
                      </span>
                      <span className="journal-dot" />
                      <strong>
                        {eventTitle[e.type] || e.type.replaceAll(".", " ")}
                      </strong>
                      <span className="event-type">{e.type}</span>
                      {e.type === "effect.unknown" && (
                        <span className="tag">RECONCILE, DON'T REDISPATCH</span>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="journal-empty">
                    <span className="journal-dot" />
                    <p>
                      {run.busy
                        ? "Waiting for the agent’s next evidence-backed action…"
                        : "Discovery complete. The provider has not been called. Review and approve the proposed recovery to begin."}
                    </p>
                    <span className="tag">
                      {run.busy ? "IN PROGRESS" : "AWAITING APPROVAL"}
                    </span>
                  </div>
                )}
              </div>
            </section>
          )}
          <footer className="action-bar">
            <div>
              <span className={`footer-symbol ${seenComplete ? "done" : ""}`}>
                {seenComplete ? (
                  <CheckCheck size={22} />
                ) : (
                  <ShieldCheck size={22} />
                )}
              </span>
              <div>
                <strong>
                  {seenComplete
                    ? `Booking ${booking?.bookingId || "confirmed"} verified`
                    : unknown
                      ? "The booking may already exist."
                      : !run
                        ? "Start with a controlled failure."
                        : valid
                          ? "Review the plan. Then let it act."
                          : "No safe route from the current inputs."}
                </strong>
                <p>
                  {seenComplete
                    ? `${receiptCount} provider receipts${quote ? ` · ${quote.priceUnits} observed cost units` : ""} · ${run?.elapsedMs ? `${(run.elapsedMs / 1000).toFixed(1)}s execution` : ""}`
                    : unknown
                      ? "Reconciliation checks the original operation before another action."
                      : !run
                        ? "Choose a fixture. Every run gets its own graph and provider ledger."
                        : valid
                          ? "Your approval is bound to the exact graph-derived plan."
                          : "Use a fresh experiment to change the scenario."}
                </p>
              </div>
            </div>
            <div className="footer-actions">
              {run && (
                <a
                  className="subtle-button"
                  href={`/api/runs/${run.runId}/export`}
                  download
                >
                  <ArrowDownToLine size={15} /> Export evidence
                </a>
              )}
              <button
                className="primary"
                disabled={
                  working ||
                  !!run?.busy ||
                  replay !== null ||
                  !!(run && !connected)
                }
                onClick={mainAction}
              >
                {run?.busy ? (
                  <>
                    <LoaderCircle size={16} className="spin" />
                    {mode === "model"
                      ? "Agent is working"
                      : "Executing recovery"}
                  </>
                ) : complete ? (
                  <>
                    Inspect the outcome <ArrowUpRight size={16} />
                  </>
                ) : run && valid ? (
                  <>
                    Review & approve <ArrowRight size={16} />
                  </>
                ) : (
                  <>
                    New recovery <Plus size={16} />
                  </>
                )}
              </button>
            </div>
          </footer>
      </>
    </>
  );
  return (
    <div className="app">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView("overview");
          }}
        >
          <span className="brand-mark">
            <GitBranch size={25} />
          </span>
          rewire<span className="brand-dot">.</span>
        </a>
        <div className="workspace-label">
          <span className="workspace-initial">R</span>
          <div>
            <strong>Operations</strong>
            <small>Local environment</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <span className="nav-caption">OPERATIONS</span>
        <nav>
          {[
            ["overview", "Overview", Activity],
            ["workspace", "Recovery run", Network],
            ["evidence", "Graph & audit", Database],
          ].map(([id, label, Icon]) => (
            <button
              key={id as string}
              className={view === id ? "active" : ""}
              onClick={() => {
                setView(id as string);
                if (id === "evidence") setTab("queries");
              }}
            >
              <Icon size={18} />
              {label as string}
              {view === id && <span className="nav-indicator" />}
            </button>
          ))}
        </nav>
        <div className="run-nav-title">
          <span className="nav-caption">RECENT RUNS</span>
          <button
            className="icon-button"
            aria-label="New recovery"
            disabled={!!run?.busy}
            onClick={() => setDialog("new")}
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="recent-runs">
          {history.slice(0, 7).map((r, i) => (
            <button
              key={r.runId}
              className={run?.runId === r.runId ? "selected" : ""}
              onClick={() => openRun(r.runId)}
            >
              <span className="run-ring" />
              <div>
                <strong>
                  {r.scenario === "carrier-d"
                    ? "Catalog change"
                    : r.scenario === "expired"
                      ? "Expired reservation"
                      : "Lost booking response"}
                </strong>
                <small>
                  {r.runId.slice(-6)} · {i === 0 ? "Latest run" : "Saved run"}
                </small>
              </div>
            </button>
          ))}
          {!history.length && <p>Your experiments will appear here.</p>}
        </div>
        <div className="sidebar-bottom">
          <div className="local-label">
            <span className="status-dot" /> LOCAL BY DESIGN
          </div>
          <p>
            Connected reasoning.
            <br />
            Traceable action.
          </p>
          <div className="sidebar-rule" />
          <div className="powered">
            <Database size={15} />
            <span>
              Powered by <strong>FalkorDB</strong>
            </span>
          </div>
          <span className="track-label">GRAPH HACKS / TRACK 01</span>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <strong>
              {view === "workspace"
                ? "Recovery run"
                : view === "overview"
                  ? "Overview"
                  : view === "evidence"
                    ? "Graph & audit"
                    : "Overview"}
            </strong>
          </div>
          <div className="runtime-status">
            <span className={health?.graph ? "online" : "offline"}>
              <i />
              FalkorDB
            </span>
            <span className={health?.modelAvailable ? "online" : "offline"}>
              <i />
              {health?.model || "Local model"}
            </span>
            <span className="synthetic-badge">SYNTHETIC ENVIRONMENT</span>
            <button className="subtle-button topbar-new" disabled={!!run?.busy} onClick={startRecoveryCase}>
              <Plus size={15} /> New recovery
            </button>
          </div>
        </header>
        <nav className="mobile-nav" aria-label="Mobile navigation">
          <button onClick={() => setView("overview")}>
            <Activity size={16} />
            Overview
          </button>
          <button onClick={() => setView("workspace")}>
            <Network size={16} />
            Recovery run
          </button>
          <button
            onClick={() => {
              setView("evidence");
              setTab("queries");
            }}
          >
            <FileCheck2 size={16} />
            Graph & audit
          </button>
          <button disabled={!!run?.busy} onClick={startRecoveryCase}>
            <Plus size={16} />
            New recovery
          </button>
        </nav>
        <main>{view === "overview" ? overview : content}</main>
        <div className="bottom-meta">
          <span>REWIRE / AGENTS THAT ACT ON CONNECTED DATA</span>
          <span>
            {run?.runId || "LOCAL WORKSPACE"}
            <i /> {connected ? "Graph stream connected" : "Local runtime"}
          </span>
        </div>
      </div>
      {dialog === "new" && (
        <Dialog
          title="Analyze shipment recovery"
          onClose={() => !working && setDialog(null)}
        >
          <p className="dialog-description">
            This isolated case uses a synthetic order and carrier ledger. Rewire
            will create a FalkorDB graph, discover the recovery plan, and wait
            for your approval before changing provider state.
          </p>
          <div className="recovery-case-summary">
            <div className="case-summary-heading"><span>CASE RW-104</span><span>SYNTHETIC FIXTURE</span></div>
            <strong>Shipment O-104 · replacement motor</strong>
            <p>Carrier A unavailable · reservation R81 held · 8 kg · destination Z3 · cost ceiling 900</p>
          </div>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={fault}
              onChange={(e) => setFault(e.target.checked)}
            />
            <div>
              <strong>Simulate a lost booking response</strong>
              <small>
                Recommended for the demo. The provider records the booking and
                then drops the reply; the agent must reconcile the same operation.
              </small>
            </div>
          </label>
          <div className="dialog-actions">
            <span>
              {health?.graph
                ? "FalkorDB is reachable"
                : "FalkorDB must be running"}
            </span>
            <button
              className="primary"
              disabled={working || !health?.graph}
              onClick={createRun}
            >
              {working ? (
                <>
                  <LoaderCircle className="spin" size={16} /> Discovering the
                  plan…
                </>
              ) : (
                <>
                  Build recovery plan <ArrowRight size={16} />
                </>
              )}
            </button>
          </div>
        </Dialog>
      )}
      {dialog === "approval" && run && (
        <Dialog
          title="Approve this recovery."
          onClose={() => !working && setDialog(null)}
        >
          <p className="dialog-description">
            Authorize the {run.plan.steps.length} proposed operations for{" "}
            {run.state.goal.orderId}. The executor validates every input again
            before dispatch.
          </p>
          <div className="approval-steps">
            {run.plan.steps.map((s) => (
              <div key={s.id}>
                <span>{s.ordinal}</span>
                <strong>{toolTitle(s.toolId)}</strong>
                <ArrowRight size={14} />
                <small>{s.expectedOutputType}</small>
              </div>
            ))}
          </div>
          <div className="approval-facts">
            <div>
              <span>Budget ceiling</span>
              <strong>{run.state.goal.maxCostUnits} units</strong>
            </div>
            <div>
              <span>Observed quote</span>
              <strong>Not yet available</strong>
            </div>
            <div>
              <span>Reservation to preserve</span>
              <strong>R81</strong>
            </div>
          </div>
          <label className="select-label">
            Execution driver
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as "model" | "direct")}
            >
              <option value="model">
                Local model → MCP tools ({health?.model})
              </option>
              <option value="direct">
                Direct MCP execution (no model inference)
              </option>
            </select>
          </label>
          {mode === "model" && !health?.modelAvailable && (
            <p className="inline-warning">
              The configured local model is unavailable. Start Ollama or
              explicitly select direct MCP execution.
            </p>
          )}
          <div className="digest">
            <ShieldCheck size={15} />
            <div>
              <strong>Approval bound to this exact plan</strong>
              <code>{run.approvalDigest}</code>
            </div>
          </div>
          <div className="dialog-actions">
            <button className="subtle-button" onClick={() => setDialog(null)}>
              Keep reviewing
            </button>
            <button
              className="primary"
              disabled={
                working ||
                !connected ||
                (mode === "model" && !health?.modelAvailable)
              }
              onClick={execute}
            >
              {working ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <ShieldCheck size={16} />
              )}{" "}
              Approve & execute
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
function BookmarkIcon() {
  return (
    <div className="preserved-icon">
      <CheckCheck size={21} />
    </div>
  );
}
function reason(code: string) {
  return (
    (
      {
        TOOL_DISABLED: "Disabled in this catalog",
        PACKAGE_WEIGHT_EXCEEDS_TOOL_LIMIT:
          "5 kg capacity · package weighs 8 kg",
        REQUIRED_SLOT_UNSATISFIED: "Required input cannot be satisfied",
        ARTIFACT_EXPIRED: "Artifact has expired",
      } as Record<string, string>
    )[code] || code.toLowerCase().replaceAll("_", " ")
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
