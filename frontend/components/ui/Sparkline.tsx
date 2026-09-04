"use client";
import { useId, useMemo } from "react";

type Props = {
  data: number[];
  width?: number;
  height?: number;
  stroke?: string;
  className?: string;
};

/** Tiny monochrome sparkline (SVG polyline, no chart lib). */
export default function Sparkline({
  data,
  width = 84,
  height = 28,
  stroke = "#000000",
  className = "",
}: Props) {
  const id = useId();
  const pts = useMemo(() => {
    const max = Math.max(...data, 1);
    const min = Math.min(...data, 0);
    const span = max - min || 1;
    return data
      .map((v, i) => {
        const x = (i / Math.max(1, data.length - 1)) * width;
        const y = height - ((v - min) / span) * (height - 4) - 2;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [data, width, height]);

  if (data.length < 2) return <span className={className} />;

  return (
    <svg
      width={width}
      height={height}
      className={className}
      style={{ filter: "drop-shadow(0 0 2px rgba(0,0,0,.2))" }}
      aria-hidden
    >
      <polyline
        points={pts}
        fill="none"
        stroke={stroke}
        strokeWidth={1.6}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <defs>
        <linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${height} ${pts} ${width},${height}`} fill={`url(#spark-${id})`} />
    </svg>
  );
}