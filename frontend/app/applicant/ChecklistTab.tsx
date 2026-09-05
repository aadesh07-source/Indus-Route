// @ts-nocheck
"use client";
import { useEffect, useState } from "react";
import { Card, Badge } from "react-bootstrap";
import { motion } from "motion/react";
import { Radio, CheckCircle2, Clock, FileText } from "lucide-react";
import type { Checklist } from "@/lib/api";

/**
 * Real-time personalised checklist board.
 * Every approval is tracked live against the applicant's actual applications —
 * no static SLA countdowns, only live clearance states synced from the officer portal.
 */

const STATUS_STYLES: Record<string, { bg: string; fg: string; label: string }> = {
  cleared: { bg: "#0a0", fg: "#fff", label: "CLEARED" },
  sent_back: { bg: "#ff9f0a", fg: "#fff", label: "SENT BACK" },
  under_review: { bg: "#000", fg: "#fff", label: "UNDER REVIEW" },
  submitted: { bg: "#333", fg: "#fff", label: "SUBMITTED" },
  drafted: { bg: "#f6f6f4", fg: "#000", label: "APPLICATION DRAFTED" },
  rejected: { bg: "#ff3b30", fg: "#fff", label: "REJECTED" },
  not_started: { bg: "transparent", fg: "#6d6d6d", label: "NOT STARTED" },
};

function liveStatus(app: any | undefined) {
  if (!app) return "not_started";
  switch (app.status) {
    case "approved":
    case "provisionally_cleared":
      return "cleared";
    case "returned":
      return "sent_back";
    case "under_review":
    case "clarification_pending":
      return "under_review";
    case "submitted":
      return "submitted";
    case "draft":
      return "drafted";
    case "rejected":
      return "rejected";
    default:
      return "not_started";
  }
}

export default function ChecklistLivePanel({ checklist, apps }: {
  checklist: Checklist | null; apps: any[];
}) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  if (!checklist || !checklist.known) return null;

  const cleared = checklist.approvals.filter((a) => {
    const app = (apps || []).find((x) => x.approval_id === a.id);
    return ["approved", "provisionally_cleared"].includes(app?.status);
  }).length;
  const active = checklist.approvals.length - cleared;
  const pad = (n: number) => String(n).padStart(2, "0");

  return (
    <Card className="stat-card h-100">
      <Card.Body>
        <div className="d-flex flex-wrap justify-content-between align-items-start gap-2">
          <div>
            <span className="kicker d-inline-flex align-items-center gap-1">
              <Radio size={11} strokeWidth={2.4} /> Personalised Checklist · Live
            </span>
            <h4 className="fw-bolder mb-1 mt-1" style={{ letterSpacing: "-0.02em" }}>
              {checklist.approvals.length} approvals tracked in real time
            </h4>
            <p style={{ color: "#6d6d6d", fontSize: ".82rem", marginBottom: 0 }}>
              {cleared} cleared · {active} in progress or awaiting action — statuses sync
              instantly with the officer portal.
            </p>
          </div>
          <div className="text-end">
            <Badge className="mono d-inline-flex align-items-center gap-1"
              style={{ background: "#f6f6f4", color: "#000", border: "1.5px solid #000", fontSize: ".62rem" }}>
              <span className="d-inline-block rounded-circle" style={{ width: 6, height: 6, background: "#0a0" }} />
              LIVE
            </Badge>
            <div className="mono" style={{ fontSize: ".7rem", color: "#6d6d6d", marginTop: 4 }}>
              {now ? `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}` : "--:--:--"}
            </div>
          </div>
        </div>

        <div className="table-modern-wrap mt-3" style={{ overflowX: "auto" }}>
          <table className="table-modern" style={{ minWidth: 620 }}>
            <thead>
              <tr>
                <th>Approval</th>
                <th>Department</th>
                <th>Parallel track</th>
                <th className="text-end">Docs</th>
                <th className="text-end">Live status</th>
              </tr>
            </thead>
            <tbody>
              {checklist.approvals.map((a, i) => {
                const app = (apps || []).find((x) => x.approval_id === a.id);
                const key = liveStatus(app);
                const st = STATUS_STYLES[key];
                const group = Object.entries(checklist.parallel_groups || {})
                  .find(([, codes]) => (codes as string[]).includes(a.code));
                return (
                  <motion.tr key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.25, delay: i * 0.04 }}>
                    <td>
                      <div className="fw-bold">
                        {a.name} {a.green_channel_eligible && (
                          <Badge style={{ background: "#000", color: "#fff", fontSize: ".62rem", padding: "2px 6px", borderRadius: 3 }}>GREEN</Badge>
                        )}
                      </div>
                      <span className="mono" style={{ fontSize: ".72rem", color: "#6d6d6d" }}>{a.code}</span>
                    </td>
                    <td style={{ fontSize: ".82rem" }}>{a.department}</td>
                    <td className="mono" style={{ fontSize: ".72rem" }}>{group ? group[0] : "—"}</td>
                    <td className="text-end">
                      <span className="d-inline-flex align-items-center gap-1" style={{ fontSize: ".78rem" }}>
                        <FileText size={11} /> {a.required_documents.length}
                      </span>
                    </td>
                    <td className="text-end">
                      <Badge className="d-inline-flex align-items-center gap-1"
                        style={{ background: st.bg, color: st.fg, border: st.bg === "transparent" ? "1.5px solid #c9c9c4" : "none", fontSize: ".62rem", fontWeight: 700, letterSpacing: ".08em", borderRadius: 3 }}>
                        {key === "cleared" ? <CheckCircle2 size={10} strokeWidth={2.6} /> :
                         key === "not_started" ? <Clock size={10} strokeWidth={2.4} /> : null}
                        {st.label}
                      </Badge>
                      {app?.sla?.state && key !== "not_started" && (
                        <div style={{ fontSize: ".62rem", color: "#6d6d6d", marginTop: 2 }}>
                          officer SLA: {app.sla.state.replace(/_/g, " ")}
                        </div>
                      )}
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="principle-bar mt-3">
          <strong>Deterministic rules decide the list</strong> — the live statuses above come
          straight from your applications and the officer portal, not from estimates.
        </div>
      </Card.Body>
    </Card>
  );
}
