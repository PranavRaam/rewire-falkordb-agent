import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  MarkerType,
  BaseEdge,
  type EdgeProps,
  type NodeProps,
  type Node,
  type Edge,
} from "@xyflow/react";
import {
  Package,
  Warehouse,
  BookmarkCheck,
  Truck,
  CalendarDays,
  ReceiptText,
  ScanLine,
  Check,
  ArrowUpRight,
  Ban,
} from "lucide-react";
import type { Run } from "./types";
import { toolTitle } from "./types";

type FlowData = {
  title: string;
  subtitle: string;
  kind: string;
  state: string;
  tag: string;
  onSelect: (id: string) => void;
  recordId: string;
};
type FlowNode = Node<FlowData>;
const icons: Record<string, typeof Package> = {
  Order: Package,
  Warehouse,
  Reservation: BookmarkCheck,
  pickup: CalendarDays,
  quote: ReceiptText,
  label: ScanLine,
  dispatch: Truck,
  blocked: Ban,
};
function Card({ data, selected }: NodeProps<FlowNode>) {
  const Icon = icons[data.kind] || Package;
  return (
    <button
      className={`flow-card ${data.state} ${selected ? "selected" : ""}`}
      onClick={() => data.onSelect(data.recordId)}
      aria-label={`${data.title}: ${data.tag}`}
    >
      <Handle type="target" position={Position.Left} />
      <span className="node-top">
        <span className="node-icon">
          <Icon size={17} />
        </span>
        <span className="node-tag">{data.tag}</span>
      </span>
      <strong>{data.title}</strong>
      <span className="node-subtitle">{data.subtitle}</span>
      <span className="node-bottom">
        {data.state === "confirmed" ? (
          <>
            <Check size={12} /> Provider confirmed
          </>
        ) : data.state === "preserved" ? (
          <>
            <Check size={12} /> Observed in graph
          </>
        ) : data.state === "blocked" ? (
          <>
            <Ban size={12} /> Unavailable
          </>
        ) : (
          <>
            <ArrowUpRight size={12} /> Inspect requirements
          </>
        )}
      </span>
      <Handle type="source" position={Position.Right} />
      <Handle id="bottom" type="source" position={Position.Bottom} />
      <Handle id="top" type="target" position={Position.Top} />
    </button>
  );
}
const nodeTypes = { record: Card };
function RoutedEdge(props: EdgeProps) {
  const { sourceX: x, sourceY: y, targetX: tx, targetY: ty, data } = props;
  const route = data?.route;
  let path = `M ${x} ${y} L ${tx} ${ty}`;
  if (route === "over")
    path = `M ${x} ${y} H ${x + 12} V -8 H ${tx - 14} V ${ty} H ${tx}`;
  if (route === "under")
    path = `M ${x} ${y} H ${x + 12} V 505 H ${tx - 14} V ${ty} H ${tx}`;
  if (route === "elbow") path = `M ${x} ${y} H ${tx - 14} V ${ty} H ${tx}`;
  return (
    <BaseEdge
      id={props.id}
      path={path}
      markerEnd={props.markerEnd}
      style={props.style}
      label={props.label}
      labelX={(x + tx) / 2}
      labelY={route === "under" ? 505 : (y + ty) / 2}
      labelStyle={props.labelStyle}
      labelBgStyle={props.labelBgStyle}
      labelBgPadding={[7, 4]}
    />
  );
}
const edgeTypes = { routed: RoutedEdge };
export function Workflow({
  run,
  selected,
  onSelect,
  replayCount,
}: {
  run: Run;
  selected: string | null;
  onSelect: (id: string) => void;
  replayCount: number | null;
}) {
  const { nodes, edges } = useMemo(() => {
    const nodes: FlowNode[] = [],
      edges: Edge[] = [];
    const events =
      replayCount === null ? run.events : run.events.slice(0, replayCount);
    const confirmed = events.filter(
      (e) => e.type === "effect.confirmed",
    ).length;
    const unknown =
      (events.filter((e) => e.type === "effect.unknown").at(-1)?.sequence ||
        0) >
      (events.filter((e) => e.type === "effect.confirmed").at(-1)?.sequence ||
        0);
    const artifacts = run.artifacts.filter((a) =>
      ["Order", "Warehouse", "Reservation"].includes(a.typeId),
    );
    const positions: Record<string, { x: number; y: number }> = {
      Order: { x: 20, y: 25 },
      Warehouse: { x: 20, y: 180 },
      Reservation: { x: 20, y: 335 },
    };
    artifacts.forEach((a) =>
      nodes.push({
        id: a.id,
        type: "record",
        position: positions[a.typeId],
        selected: selected === a.id,
        data: {
          recordId: a.id,
          onSelect,
          title:
            a.typeId === "Reservation"
              ? `Reservation ${a.reservationId}`
              : a.typeId === "Order"
                ? `Order ${run.state.goal.orderId}`
                : `Warehouse ${run.state.goal.warehouseId}`,
          subtitle:
            a.typeId === "Reservation"
              ? "Existing stock allocation"
              : a.typeId === "Order"
                ? `${run.state.goal.weightKg} kg · Replacement motor`
                : "Origin · inventory ready",
          kind: a.typeId,
          state:
            run.scenario === "expired" && a.typeId === "Reservation"
              ? "blocked"
              : "preserved",
          tag:
            run.scenario === "expired" && a.typeId === "Reservation"
              ? "EXPIRED"
              : "EXISTING",
        },
      }),
    );
    run.plan.steps.forEach((s, i) => {
      const receipt = run.executionSteps.find(
        (e) => e.ordinal === s.ordinal,
      )?.receiptId;
      const done = replayCount === null ? !!receipt : i < confirmed;
      const kind = s.adapterId.split("-").at(-1) || "dispatch";
      const state = done
        ? "confirmed"
        : unknown && i === 3
          ? "unknown"
          : "proposed";
      const position = [
        { x: 250, y: 180 },
        { x: 480, y: 180 },
        { x: 480, y: 335 },
        { x: 710, y: 335 },
      ][i] || { x: 330 + i * 240, y: 235 };
      nodes.push({
        id: s.id,
        type: "record",
        position,
        selected: selected === s.id,
        data: {
          recordId: s.id,
          onSelect,
          title:
            kind === "dispatch"
              ? "Book shipment"
              : kind === "pickup"
                ? "Schedule pickup"
                : kind === "quote"
                  ? "Get a quote"
                  : "Create label",
          subtitle: toolTitle(s.toolId),
          kind,
          state,
          tag: done
            ? "CONFIRMED"
            : state === "unknown"
              ? "UNKNOWN"
              : `STEP 0${i + 1}`,
        },
      });
      s.inputs.forEach((input, j) =>
        edges.push({
          id: `${s.id}-${j}`,
          source: input.artifactId || input.producerStepId || "",
          target: s.id,
          type: "routed",
          sourceHandle: input.producerStepId && i === 2 ? "bottom" : undefined,
          targetHandle: input.producerStepId && i === 2 ? "top" : undefined,
          data: {
            route:
              input.typeId === "Order"
                ? "over"
                : input.typeId === "Reservation" ||
                    (i === 3 && input.producerStepId === run.plan.steps[0]?.id)
                  ? "under"
                  : i === 3 && input.producerStepId === run.plan.steps[1]?.id
                    ? "elbow"
                    : "direct",
          },
          animated: run.busy && !done,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 13,
            height: 13,
            color: done ? "#6c7848" : "#ac998b",
          },
          style: {
            stroke: done ? "#7c8954" : "#ac998b",
            strokeWidth: 1.6,
            strokeDasharray: done ? undefined : "5 5",
          },
          label:
            input.typeId === "Reservation" ? "preserve & reuse" : undefined,
          labelStyle: { fontSize: 11, fill: "#6f654f" },
          labelBgStyle: { fill: "#f6f3ec" },
          labelBgPadding: [7, 4],
        }),
      );
    });
    const unavailable = run.plan.rejected.filter(
      (r) => r.reasonCode === "TOOL_DISABLED" && r.toolId?.includes("dispatch"),
    );
    unavailable.slice(0, 2).forEach((r, i) =>
      nodes.push({
        id: r.toolId!,
        type: "record",
        position: { x: 480 + i * 230, y: 25 },
        selected: selected === r.toolId,
        data: {
          recordId: r.toolId!,
          onSelect,
          title: toolTitle(r.toolId!).replace(" Dispatch", ""),
          subtitle: "Disabled in this scenario",
          kind: "blocked",
          state: "blocked",
          tag: "UNAVAILABLE",
        },
      }),
    );
    return { nodes, edges };
  }, [run, selected, onSelect, replayCount]);
  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      fitView
      fitViewOptions={{ padding: 0.07 }}
      minZoom={0.35}
      maxZoom={1.5}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      onNodeClick={(_, n) => onSelect(n.id)}
      preventScrolling={false}
      aria-label="Graph-derived recovery workflow"
    >
      <Background color="#ddd5c8" gap={22} size={1} />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
