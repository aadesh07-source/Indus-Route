"use client";
import { useEffect, useState } from "react";

type Props = {
  value: number;
  duration?: number;
  suffix?: string;
  prefix?: string;
  decimals?: number;
  className?: string;
};

export default function CountUp({
  value,
  duration = 1200,
  suffix = "",
  prefix = "",
  decimals = 0,
  className = "",
}: Props) {
  const [n, setN] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let cancelled = false;
    import("animejs").then(({ default: anime }) => {
      if (cancelled) return;
      const obj = { v: 0 };
      const anim = anime({
        targets: obj,
        v: value,
        duration,
        easing: "easeOutExpo",
        update: () => setN(obj.v),
      });
      return () => anim.pause();
    });
    return () => { cancelled = true; };
  }, [value, duration]);

  const display = decimals > 0 ? n.toFixed(decimals) : String(Math.round(n));
  return (
    <span className={className}>
      {prefix}
      {display}
      {suffix}
    </span>
  );
}