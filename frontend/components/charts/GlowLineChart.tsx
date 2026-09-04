"use client";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export type TrendDatum = { label: string; applications: number };

export function InkTooltip({ active, payload, label, suffix = "" }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip-ink">
      <div className="tt-k">{label}</div>
      <div className="fw-bold">{payload[0].value}
        <span className="tt-k">{suffix}</span>
      </div>
    </div>
  );
}

/**
 * Thin-stroke glowing-green line chart on black. Minimal gridlines,
 * white/gray axis labels only.
 */
export default function GlowLineChart({
  data,
  stroke = "#000000",
  dataKey = "applications",
  height = 230,
}: {
  data: TrendDatum[];
  stroke?: string;
  dataKey?: string;
  height?: number;
}) {
  return (
    <div className="chart-shell" style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 6, left: -24, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#2a2a2a" strokeDasharray="2 4" />
          <XAxis
            dataKey="label"
            axisLine={{ stroke: "#2a2a2a" }}
            tickLine={false}
            tick={{ fill: "#8f8f8f", fontSize: 11, fontFamily: "monospace" }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#8f8f8f", fontSize: 11, fontFamily: "monospace" }}
          />
          <Tooltip content={<InkTooltip />} cursor={{ stroke: "#3a3a3a" }} />
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={stroke}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: stroke, strokeWidth: 0 }}
            style={{ filter: "drop-shadow(0 0 3px rgba(0,0,0,.25))" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}