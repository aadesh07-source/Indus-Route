"use client";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

export type DonutDatum = { name: string; value: number };

const PALETTE = ["#000000", "#4a4a4a", "#6d6d6d", "#9a9a9a", "#c9c9c4", "#e5e5e1"];

function DonutTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div className="tooltip-ink">
      <div className="tt-k">{d.name}</div>
      <div className="fw-bold">{d.value}
        <span className="tt-k">×</span>
      </div>
    </div>
  );
}

/**
 * Deficiency-cause donut on black — monochrome rings, green for the top
 * deficiency only.
 */
export default function DeficiencyDonut({
  data,
  height = 230,
}: {
  data: DonutDatum[];
  height?: number;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="chart-shell" style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            innerRadius={46}
            outerRadius={86}
            paddingAngle={2}
            dataKey="value"
            stroke="none"
          >
            {data.map((d, i) => (
              <Cell
                key={i}
                fill={PALETTE[i % PALETTE.length]}
                style={
                  d.value === max
                    ? { filter: "drop-shadow(0 0 4px rgba(0,0,0,.3))" }
                    : undefined
                }
              />
            ))}
          </Pie>
          <Tooltip content={<DonutTooltip />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}