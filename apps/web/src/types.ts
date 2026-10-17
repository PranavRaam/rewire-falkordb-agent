export type Binding = {
  slotId: string;
  typeId: string;
  artifactId?: string;
  artifactVersion?: number;
  producerStepId?: string;
};
export type Step = {
  id: string;
  ordinal: number;
  toolId: string;
  adapterId: string;
  expectedOutputType: string;
  inputs: Binding[];
};
export type Evidence = {
  queryId: string;
  query: string;
  sha256: string;
  elapsedMs: number;
  rowCount: number;
  params: Record<string, unknown>;
  rows: Record<string, unknown>[];
};
export type Plan = {
  status: string;
  steps: Step[];
  preservedArtifacts: string[];
  rejected: {
    toolId?: string;
    reasonCode: string;
    observed?: Record<string, unknown>;
    artifactId?: string;
  }[];
  blockers: { typeId: string; reasonCode: string }[];
  evidence: Evidence[];
  exploredExpansions: number;
};
export type Artifact = {
  id: string;
  typeId: string;
  status: string;
  version: number;
  reservationId?: string;
  bookingId?: string;
  priceUnits?: number;
  expiresAt: number;
  responseJson?: string;
  [key: string]: unknown;
};
export type Run = {
  runId: string;
  graphName: string;
  scenario: string;
  createdAt: string;
  nowMs: number;
  faultAfterCommit: boolean;
  approvalDigest: string | null;
  plan: Plan;
  busy: boolean;
  interrupted: boolean;
  error?: string;
  jobStatus: string;
  elapsedMs?: number;
  executionMode?: string;
  executionResult?: {
    status: string;
    model?: string;
    final?: string;
    toolTrace?: {
      tool: string;
      status: string;
      round: number;
      result?: unknown;
    }[];
  };
  state: {
    runStatus: string;
    revision: number;
    goal: {
      orderId: string;
      warehouseId: string;
      destinationZone: string;
      weightKg: number;
      maxCostUnits: number;
      cutoffAt: number;
    };
  };
  executionSteps: {
    ordinal: number;
    status: string;
    intentStatus: string;
    operationKey: string;
    receiptId: string;
    providerRecordId: string;
  }[];
  artifacts: Artifact[];
  events: { sequence: number; type: string; timestamp: number }[];
};
export type Health = { graph: boolean; model: string; modelAvailable: boolean };
export type Audit = {
  source: string;
  visibleToAgent: boolean;
  rowCounts: Record<string, number>;
  bookings: Record<string, unknown>[];
};
export type Scenario = {
  id: string;
  name: string;
  subtitle: string;
  description: string;
};
export type RunSummary = {
  runId: string;
  scenario: string;
  createdAt: string;
  jobStatus: string;
};
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(
    "/api" + path,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Rewire-Client": "control-room",
          },
          body: JSON.stringify(body),
        },
  );
  if (!res.ok) {
    const value = await res.json().catch(() => ({}));
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : "Request failed. Check the local services.",
    );
  }
  return res.json();
}
export const pretty = (value: unknown) => JSON.stringify(value, null, 2);
export const toolTitle = (id: string) =>
  id
    .replace(/^tool:/, "")
    .replace(/:v\d+$/, "")
    .split("-")
    .map((x) =>
      x.length === 1 ? x.toUpperCase() : x[0].toUpperCase() + x.slice(1),
    )
    .join(" ");
export const eventTitle: Record<string, string> = {
  "plan.selected": "Exact recovery plan approved",
  "intent.prepared": "Intent persisted before dispatch",
  "attempt.started": "Provider operation submitted",
  "effect.unknown": "Booking response lost · outcome unknown",
  "status.started": "Looking up the original operation",
  "effect.confirmed": "Provider receipt confirmed",
  "artifact.observed": "Confirmed output added to the graph",
  "run.succeeded": "Shipment confirmed in FalkorDB",
  "plan.approved": "Exact recovery plan approved",
  "intent.claimed": "Intent persisted before dispatch",
  "attempt.dispatched": "Provider operation submitted",
  "reconciliation.started": "Looking up the original operation",
  "effect.attempt_started": "Provider operation submitted",
  "effect.reconciliation_started": "Looking up the original operation",
  "effect.prepared": "Intent persisted before dispatch",
};
