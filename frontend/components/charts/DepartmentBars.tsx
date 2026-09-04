"use client";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { InkTooltip } from "./GlowLineChart";

export type DeptBarDatum = {
  department: string;
  applications: number;
  avgSlaDays: number;
};

/**
 * Rounded-bar department bottleneck chart on black. White bars, the
 * busiest department turned electric green.
 */
export default function DepartmentBars({
  data,
  height = 240,
}: {
  data: DeptBarDatum[];
  height?: number;
}) {
  const max = Math.max(1, ...data.map((d) => d.applications));
  return (
    <div className="chart-shell" style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid stroke="#2a2a2a" strokeDasharray="2 4" horizontal={false} />
          <XAxis
            type="number"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#8f8f8f", fontSize: 11, fontFamily: "monospace" }}
          />
          <YAxis
            type="category"
            dataKey="department"
            width={168}
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#c9c9c4", fontSize: 11 }}
          />
          <Tooltip content={<InkTooltip />} cursor={{ fill: "rgba(255,255,255,.05)" }} />
          <Bar dataKey="applications" radius={[0, 4, 4, 0]} barSize={15}>
            {data.map((d, i) => (
              <Cell
                key={i}
                fill={d.applications === max ? "#000000" : "#c9c9c4"}
                style={
                  d.applications === max
                    ? { filter: "drop-shadow(0 0 3px rgba(0,0,0,.3))" }
                    : undefined
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}