// @ts-nocheck
"use client";
// Shared monochrome analytics widgets — recharts is loaded client-side
// only (NextDynamic ssr:false) so SSR markup stays deterministic.
import dynamic from "next/dynamic";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";

const Recharts = {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
};
void Recharts;

function InkTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip-ink">
      <div className="tt-k">{label ?? payload[0].name}</div>
      <div className="fw-bold">{payload[0].value}</div>
    </div>
  );
}

// ── Monochrome palette (strict black/white identity) ──────────
export const INK_PALETTE = ["#000000", "#4a4a4a", "#6d6d6d", "#9a9a9a", "#c9c9c4", "#e5e5e1"];

export function DonutChart({ data, height = 220, inner = 42, outer = 74 }: {
  data: { name: string; value: number }[];
  height?: number;
  inner?: number;
  outer?: number;
}) {
  if (!data?.length) return <div style={{ height }} />;
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <PieChart>
          <Pie data={data} innerRadius={inner} outerRadius={outer} paddingAngle={3}
            dataKey="value" stroke="#fff" strokeWidth={2}>
            {data.map((d, i) => (
              <Cell key={i} fill={INK_PALETTE[i % INK_PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip content={<InkTip />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function VerticalBars({ data, height = 220, color = "#000000" }: {
  data: { name: string; value: number }[];
  height?: number;
  color?: string;
}) {
  if (!data?.length) return <div style={{ height }} />;
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#ecece8" strokeDasharray="2 4" />
          <XAxis dataKey="name" axisLine={{ stroke: "#000" }} tickLine={false}
            tick={{ fill: "#6d6d6d", fontSize: 10, fontFamily: "monospace" }}
            interval={0} angle={-14} textAnchor="end" height={46} />
          <YAxis axisLine={false} tickLine={false} allowDecimals={false}
            tick={{ fill: "#6d6d6d", fontSize: 10, fontFamily: "monospace" }} />
          <Tooltip content={<InkTip />} cursor={{ fill: "rgba(0,0,0,.04)" }} />
          <Bar dataKey="value" fill={color} radius={[5, 5, 0, 0]} barSize={26} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function HorizontalBars({ data, height = 220 }: {
  data: { name: string; value: number }[];
  height?: number;
}) {
  if (!data?.length) return <div style={{ height }} />;
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 20, left: 8, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke="#ecece8" strokeDasharray="2 4" />
          <XAxis type="number" axisLine={false} tickLine={false} allowDecimals={false}
            tick={{ fill: "#6d6d6d", fontSize: 10, fontFamily: "monospace" }} />
          <YAxis type="category" dataKey="name" width={130} axisLine={false} tickLine={false}
            tick={{ fill: "#000", fontSize: 10.5 }} />
          <Tooltip content={<InkTip />} cursor={{ fill: "rgba(0,0,0,.04)" }} />
          <Bar dataKey="value" fill="#000000" radius={[0, 5, 5, 0]} barSize={14} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// Client-only re-export guard: consumers should dynamic-import this
// module so recharts never lands in the SSR bundle.
export default null;
