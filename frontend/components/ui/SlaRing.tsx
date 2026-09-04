"use client";
import { useMemo } from "react";

type Props = {
  value: number; // remaining 0..1
  size?: number;
  strokeWidth?: number;
  color?: string;
};

/**
 * Thin circular ring badge — status encoded purely by ring color.
 * No Bootstrap Badge fill; a Bootstrap Badge can wrap the numeric label
 * beside it at the call site.
 */
export default function SlaRing({
  value,
  size = 56,
  strokeWidth = 4,
  color = "#000000",
}: Props) {
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const clamped = useMemo(() => Math.max(0, Math.min(1, value)), [value]);
  return (
    <span className="sla-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#e5e5e1"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={c}
          strokeDashoffset={c * (1 - clamped)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          strokeLinecap="butt"
        />
      </svg>
      <span className="sla-ring-num">{Math.round(clamped * 100)}%</span>
    </span>
  );
}