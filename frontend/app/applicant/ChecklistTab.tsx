// @ts-nocheck
"use client";
import { Card, ListGroup, Badge } from "react-bootstrap";
import { motion } from "motion/react";
import { CheckCircle2, XCircle } from "lucide-react";
import SlaRing from "@/components/ui/SlaRing";
import type { Checklist } from "@/lib/api";

export default function ChecklistTab({ checklist, aiSummary }: { checklist: Checklist | null; aiSummary: any }) {
  if (!checklist || !checklist.known) return (
    <Card><Card.Body className="text-center py-5" style={{ color: "#6d6d6d" }}>
      <p>Save your business profile to generate a personalised checklist.</p>
    </Card.Body></Card>
  );

  return (
    <div className="row g-3">
      <div className="col-lg-8">
        <Card className="stat-card">
          <Card.Body>
            <span className="kicker">Personalised Checklist</span>
            <h4 className="fw-bolder mb-1 mt-1" style={{ letterSpacing: "-0.02em" }}>
              {checklist.approvals.length} approvals required · {checklist.max_sla_days} day max SLA
            </h4>
            <p style={{ color: "#6d6d6d", fontSize: ".82rem" }}>{checklist.note}</p>
            <div className="table-modern-wrap mt-3" style={{ overflowX: "auto" }}>
              <table className="table-modern" style={{ minWidth: 540 }}>
                <thead>
                  <tr>
                    <th>Approval</th>
                    <th>Department</th>
                    <th className="text-end">SLA (days)</th>
                    <th className="text-end">Docs</th>
                    <th className="text-end">Track</th>
                  </tr>
                </thead>
                <tbody>
                  {checklist.approvals.map((a, i) => (
                    <motion.tr key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: i * 0.05 }}>
                      <td>
                        <div className="fw-bold">{a.name} {a.green_channel_eligible && (
                          <Badge style={{ background: "#000", color: "#fff", fontSize: ".62rem", padding: "2px 6px", borderRadius: 3 }}>GREEN</Badge>
                        )}</div>
                        <span className="mono" style={{ fontSize: ".72rem", color: "#6d6d6d" }}>{a.code}</span>
                      </td>
                      <td style={{ fontSize: ".82rem" }}>{a.department}</td>
                      <td className="text-end fw-bold">{a.sla_days}</td>
                      <td className="text-end">{a.required_documents.length}</td>
                      <td className="text-end"><SlaRing value={a.sla_days / 60} size={44} strokeWidth={3} /></td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card.Body>
        </Card>
      </div>
      <div className="col-lg-4">
        {aiSummary && (
          <Card className="stat-card ai-summary-card">
            <Card.Body>
              <span className="kicker" style={{ color: "#8f8f8f" }}>AI summary</span>
              <h5 className="fw-bold mb-2 mt-1">How to think about this</h5>
              <p style={{ fontSize: ".82rem", color: "#c9c9c4" }}>{aiSummary.text}</p>
              <div className="principle-bar mt-3"><strong>Advisory only</strong> — rules decided this checklist.</div>
            </Card.Body>
          </Card>
        )}
        {Object.keys(checklist.parallel_groups).length > 0 && (
          <Card className="stat-card mt-3">
            <Card.Body>
              <h5 className="fw-bold mb-2">Parallel groups</h5>
              {Object.entries(checklist.parallel_groups).map(([g, codes]) => (
                <div key={g} className="d-flex justify-content-between py-1" style={{ borderBottom: "1px solid #ecece8", fontSize: ".78rem" }}>
                  <span className="mono fw-bold">{g}</span><span style={{ color: "#6d6d6d" }}>{codes.length} approvals</span>
                </div>
              ))}
            </Card.Body>
          </Card>
        )}
      </div>
    </div>
  );
}
