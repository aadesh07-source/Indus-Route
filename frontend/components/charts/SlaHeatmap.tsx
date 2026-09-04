// @ts-nocheck
"use client";
import { OverlayTrigger, Tooltip } from "react-bootstrap";

export type HeatCell = {
  day: string;
  date: string;
  severity: 0 | 1 | 2 | 3 | 4;
  note: string;
};

/**
 * SLA-breach heatmap — cells glow green → amber → red by severity.
 * Hover shows a Bootstrap Tooltip.
 */
export default function SlaHeatmap({ cells, cols = 6 }: { cells: HeatCell[]; cols?: number }) {
  return (
    <div className="sla-heat" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
      {cells.map((c, i) => (
        <OverlayTrigger key={i} placement="top" overlay={<Tooltip id={`heat-${i}`}>{c.note}</Tooltip>}>
          <div className={`heat-cell sev${c.severity}`} role="img" aria-label={c.note}>
            <span className="heat-day">{c.day}</span>
          </div>
        </OverlayTrigger>
      ))}
    </div>
  );
}