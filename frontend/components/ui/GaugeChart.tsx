"use client";
import { useEffect, useState } from "react";

type Props = {
  value: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  trackColor?: string;
  fillColor?: string;
  glow?: boolean;
};

/**
 * Circular SVG gauge. anime.js animates the stroke-dashoffset AND the
 * count-up number in sync — 1200ms easeOutExpo.
 */
export default function GaugeChart({
  value,
  size = 230,
  strokeWidth = 11,
  label,
  trackColor = "#e5e5e1",
  fillColor = "#000000",
  glow = false,
}: Props) {
  const [offset, setOffset] = useState(0);
  const [num, setNum] = useState(0);
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;

  useEffect(() => {
    if (typeof window === "undefined") return;
    let cancelled = false;
    import("animejs").then(({ default: anime }) => {
      if (cancelled) return;
      const obj = { v: 0 };
      const anim = anime({
        targets: obj,
        v: Math.max(0, Math.min(100, value)),
        duration: 1200,
        easing: "easeOutExpo",
        round: 1,
        update: () => {
          setOffset(c * (1 - obj.v / 100));
          setNum(obj.v);
        },
      });
      return () => anim.pause();
    });
    return () => { cancelled = true; };
  }, [value, c]);

  return (
    <div className="gauge-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} role="img" aria-label={label ?? "score"}>
        <circle
          className="gauge-track"
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={trackColor}
          strokeWidth={strokeWidth}
        />
        <circle
          className="gauge-fill"
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={fillColor}
          strokeWidth={strokeWidth}
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="butt"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={glow ? { filter: "drop-shadow(0 0 6px rgba(0,0,0,.25))" } : undefined}
        />
      </svg>
      <div className="gauge-num">{Math.round(num)}%</div>
    </div>
  );
}