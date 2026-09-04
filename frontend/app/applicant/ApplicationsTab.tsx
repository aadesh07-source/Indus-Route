// @ts-nocheck
"use client";
import { useState } from "react";
import { Card, Button, Form, ProgressBar, Badge } from "react-bootstrap";
import Link from "next/link";
import { motion } from "motion/react";
import { FileCheck2, PlusCircle, Upload } from "lucide-react";
import { createApplication, submitApplication } from "@/lib/api";
import SlaRing from "@/components/ui/SlaRing";

type AppRow = {
  id: string; status: string; approval_name: string; approval_code: string;
  department: string; sla_days: number; readiness_score: number;
  sla: { state: string; remaining_hours: number | null }; green_channel: boolean;
  provisional_certificate: any; documents?: any[];
};

export default function ApplicationsTab({ apps, reload, setMsg, setErr }: {
  apps: AppRow[]; reload: () => void; setMsg: (s: string) => void; setErr: (s: string) => void;
}) {
  const [appId, setAppId] = useState("");

  async function apply(checklistApprovalId: string) {
    setErr(""); setMsg("");
    try { await createApplication(checklistApprovalId); setMsg("Application created."); reload(); }
    catch (e: any) { setErr(e.message); }
  }
  async function submit(id: string) {
    setErr(""); setMsg("");
    try { await submitApplication(id); setMsg("Submitted for review."); reload(); }
    catch (e: any) { setErr(e.message); }
  }

  return (
    <div className="row g-3">
      <div className="col-lg-8">
        <Card className="stat-card">
          <Card.Body>
            <h5 className="fw-bold mb-3">Your Applications</h5>
            {apps.length === 0 ? (
              <div className="text-center py-4" style={{ color: "#6d6d6d" }}>
                <FileCheck2 size={28} strokeWidth={1.2} className="mb-2" />
                <p style={{ fontSize: ".82rem" }}>No applications yet.</p>
              </div>
            ) : (
              <div className="table-responsive">
                <table className="table table-borderless align-middle">
                  <thead><tr style={{ borderBottom: "1.5px solid #000" }}>
                    <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>ID</th>
                    <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>Approval</th>
                    <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>Status</th>
                    <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>Readiness</th>
                    <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>SLA</th>
                    <th></th>
                  </tr></thead>
                  <tbody>
                    {apps.map(a => (
                      <tr key={a.id} style={{ borderBottom: "1px solid #ecece8" }}>
                        <td className="mono" style={{ fontSize: ".74rem" }}>{a.id.slice(-8)}</td>
                        <td><span className="fw-bold">{a.approval_code}</span><div style={{ color: "#6d6d6d", fontSize: ".72rem" }}>{a.department}</div></td>
                        <td><Badge style={{ background: "transparent", color: "#000", border: "1.5px solid #000", borderRadius: 3, fontSize: ".64rem", fontWeight: 700 }}>
                          {a.status.replace(/_/g, " ").toUpperCase()}
                        </Badge></td>
                        <td>
                          <div className="d-flex align-items-center gap-2">
                            <ProgressBar now={a.readiness_score || 0} max={100} style={{ flex: 1, height: 4, borderRadius: 0, background: "#e7e7e2" }} />
                            <span className="mono" style={{ fontSize: ".72rem" }}>{a.readiness_score || 0}%</span>
                          </div>
                        </td>
                        <td><SlaRing value={a.sla?.remaining_hours ? Math.max(0, a.sla.remaining_hours) / (a.sla_days * 24) : 1} size={38} strokeWidth={3}
                          color={a.sla?.state === "breached" ? "#ff3b30" : a.sla?.state === "at_risk" ? "#ff9f0a" : "#000"} /></td>
                        <td className="text-end">
                          {a.status === "draft" && (
                            <div className="d-flex gap-1 justify-content-end">
                              <Button size="sm" className="btn-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }} onClick={() => submit(a.id)}>Submit</Button>
                              <Link href={`/applicant/upload?app=${a.id}`}>
                                <Button size="sm" className="btn-mono btn-outline-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }}>Docs</Button>
                              </Link>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card.Body>
        </Card>
      </div>
      <div className="col-lg-4">
        <Card className="stat-card">
          <Card.Body>
            <span className="kicker">Quick create</span>
            <h5 className="fw-bold mb-2 mt-1">New application</h5>
            <Form.Group className="mb-3">
              <Form.Label style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", fontWeight: 700 }}>Checklist approval ID</Form.Label>
              <Form.Control value={appId} onChange={e => setAppId(e.target.value)} placeholder="approval-uuid-here" className="mono" style={{ fontSize: ".82rem" }} />
            </Form.Group>
            <Button className="btn-mono w-100" disabled={!appId} onClick={() => apply(appId)}>
              <PlusCircle size={14} strokeWidth={2} /> Create Application
            </Button>
            <div className="principle-bar mt-3"><strong>Tip:</strong> Copy the approval ID from your checklist.</div>
          </Card.Body>
        </Card>
      </div>
    </div>
  );
}
