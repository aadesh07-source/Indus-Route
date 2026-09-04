// @ts-nocheck
"use client";
import { Card, Row, Col } from "react-bootstrap";
import { LucideIcon } from "lucide-react";
import dynamic from "next/dynamic";
import Sparkline from "./Sparkline";
const CountUp = dynamic(() => import("./CountUp"), { ssr: false });

type Props = {
  icon: LucideIcon;
  label: string;
  value: number;
  suffix?: string;
  spark?: number[];
  note?: string;
  index?: number;
};

/**
 * White-surface Bootstrap Card stat tile: black 1.5px border, count-up
 * number, electric-green sparkline. `index` adds a motion.dev stagger.
 */
export default function StatCard({
  icon: Icon,
  label,
  value,
  suffix = "",
  spark = [],
  note,
  index = 0,
}: Props) {
  return (
    <Card className="stat-card h-100">
      <Card.Body className="d-flex flex-column gap-2">
        <div className="d-flex justify-content-between align-items-start">
          <span className="stat-icon">
            <Icon size={18} strokeWidth={1.75} />
          </span>
          {spark.length >= 2 && (
            <span className="spark-wrap">
              <Sparkline data={spark} />
            </span>
          )}
        </div>
        <div className="stat-num">
          <CountUp value={value} suffix={suffix} />
        </div>
        <div className="stat-lbl">
          {label}
          {note && <span className="d-block" style={{ color: "#a0a0a0", letterSpacing: ".04em", textTransform: "none", marginTop: 4 }}>{note}</span>}
        </div>
      </Card.Body>
    </Card>
  );
}