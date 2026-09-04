"use client";
import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";

export type DagNodeData = {
  code: string;
  name: string;
  status: "pending" | "approved" | "flagged";
  greenChannel: boolean;
};

/**
 * Line-based DAG node — status via border color ONLY (black pending,
 * electric-green approved, pure-red flagged). No fills.
 */
function DAGNode({ data }: NodeProps<DagNodeData>) {
  const cls =
    data.status === "approved"
      ? "node-approved"
      : data.status === "flagged"
      ? "node-flagged"
      : "";
  const label =
    data.status === "approved"
      ? "Approved"
      : data.status === "flagged"
      ? "Flagged"
      : data.greenChannel
      ? "Green channel"
      : "Pending";

  return (
    <div className={`dag-node ${cls}`}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} isConnectable={false} />
      <div className="dag-code">{data.code}</div>
      <div className="fw-bold" style={{ lineHeight: 1.18, margin: "0.1rem 0 0.15rem" }}>
        {data.name}
      </div>
      <div className="dag-status">{label}</div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} isConnectable={false} />
    </div>
  );
}

export default memo(DAGNode);