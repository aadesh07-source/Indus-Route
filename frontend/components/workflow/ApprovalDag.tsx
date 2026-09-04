"use client";
import { useMemo } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import DAGNode, { type DagNodeData } from "./DAGNode";
import type { Checklist, ChecklistApproval } from "@/lib/api";

type Props = {
  checklist: Checklist;
  statusOf: (approval: ChecklistApproval) => "pending" | "approved" | "flagged";
};

function statusToData(a: ChecklistApproval, status: Props["statusOf"]) {
  return {
    code: a.code,
    name: a.name,
    status: status(a),
    greenChannel: a.green_channel_eligible,
  } as DagNodeData;
}

/**
 * Approval DAG — parallel groups stacked in columns, dependencies as edges.
 * Pure line language: no node fills, no swipe shadows.
 */
export default function ApprovalDag({ checklist, statusOf }: Props) {
  const { nodes, edges } = useMemo(() => {
    const approvals = checklist.approvals ?? [];
    const groups = Array.from(
      new Set(approvals.map((a) => a.parallel_group || "sequential"))
    ).sort();

    const codeToId: Record<string, string> = {};
    const nodes: Node<DagNodeData>[] = [];
    const edges: Edge[] = [];

    // Index positions per group so nodes never overlap.
    const groupIndex: Record<string, number> = {};
    groups.forEach((g, i) => {
      groupIndex[g] = i;
    });

    approvals.forEach((a, order) => {
      const g = a.parallel_group || "sequential";
      const gi = groupIndex[g];
      const inGroup = approvals.filter((x) => (x.parallel_group || "sequential") === g);
      const posInGroup = inGroup.findIndex((x) => x.id === a.id);
      const horizontal = 70 + gi * 300;
      const vertical = 70 + posInGroup * 130;
      const nodeId = a.code;
      codeToId[a.code] = nodeId;
      const node: Node<DagNodeData> = {
        id: nodeId,
        position: { x: horizontal, y: vertical },
        data: statusToData(a, statusOf),
        type: "dag",
      };
      nodes.push(node);

      for (const dep of a.dependency_ids || []) {
        if (codeToId[dep]) {
          edges.push({
            id: `${dep}->${a.code}`,
            source: codeToId[dep],
            target: nodeId,
            animated: false,
            markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: "#000" },
            style: { stroke: "#000", strokeWidth: 1.6 },
          });
        }
      }
    });

    // Chain each parallel group into the next (parallel → sequential flow).
    for (let i = 1; i < groups.length; i++) {
      const prevGroup = groups[i - 1];
      const nextGroup = groups[i];
      const prevLast = approvals
        .filter((a) => (a.parallel_group || "sequential") === prevGroup)
        .at(-1);
      const nextFirst = approvals
        .filter((a) => (a.parallel_group || "sequential") === nextGroup)[0];
      if (prevLast && nextFirst) {
        edges.push({
          id: `chain-${prevGroup}-${nextGroup}`,
          source: codeToId[prevLast.code],
          target: codeToId[nextFirst.code],
          style: { stroke: "#9a9a9a", strokeWidth: 1, strokeDasharray: "4 4" },
        });
      }
    }

    return { nodes, edges };
  }, [checklist, statusOf]);

  return (
    <div className="dag-shell">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={{ dag: DAGNode }}
        fitView
        fitViewOptions={{ padding: 0.28 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
        minZoom={0.4}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#d4d4d0" />
        <Controls showInteractive={false} style={{ borderRadius: 4 }} />
      </ReactFlow>
    </div>
  );
}