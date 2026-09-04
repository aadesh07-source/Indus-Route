// @ts-nocheck
"use client";
import { useCallback, useEffect, useState } from "react";
import { Container, Row, Col, Card, Button, Table } from "react-bootstrap";
import { motion } from "motion/react";
import { AlertTriangle, Clock, CheckCircle2, ClipboardCheck, Shield } from "lucide-react";
import { getToken, setToken, getOfficerQueue } from "@/lib/api";
import StatCard from "@/components/ui/StatCard";
import AttentionTag from "@/components/ui/AttentionTag";
import SlaRing from "@/components/ui/SlaRing";
import OfficerReviewPanel from "./ReviewPanel";
import NextDynamic from "next/dynamic";

const DonutChart = NextDynamic(() => import("@/components/ui/charts").then(m => m.DonutChart), { ssr: false });
const VerticalBars = NextDynamic(() => import("@/components/ui/charts").then(m => m.VerticalBars), { ssr: false });

type QueueEntry = {
  id: string; approval_name: string; approval_code: string; business_name: string;
  status: string; readiness_score: number; attention: string;
  sla: { state: string; remaining_hours: number | null };
  assigned_officer_id: string | null; my_assignment: boolean; documents: any[];
};

const TH = { fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" as const };

export default function OfficerPortal() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [queue, setQueue] = useState<{ assigned: QueueEntry[]; unassigned: QueueEntry[] } | null>(null);
  const [selected, setSelected] = useState<QueueEntry | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const loadQueue = useCallback(async () => {
    try { const q = await getOfficerQueue(); setQueue(q); setAuthed(true); }
    catch { setAuthed(false); }
  }, []);

  useEffect(() => { setAuthed(getToken() ? null : false); }, []);
  useEffect(() => { if (authed === null) loadQueue(); }, [authed, loadQueue]);

  if (authed === false) return (
    <Container fluid="xxl" className="py-5"><Card className="mx-auto" style={{ maxWidth: 520 }}>
      <Card.Body className="p-4 text-center"><Shield size={32} strokeWidth={1.5} className="mb-3" /><h2 className="display-7 mb-2">Officer Portal</h2>
        <p style={{ color: "#6d6d6d" }}>Officer login required.</p><a href="/login" className="btn btn-mono mt-2">Sign in</a></Card.Body>
    </Card></Container>
  );

  const totalAssigned = queue?.assigned.length || 0;
  const all = [...(queue?.assigned || []), ...(queue?.unassigned || [])];
  const highAttention = all.filter(q => q.attention === "high").length;
  const slaBreached = all.filter(q => q.sla?.state === "breached").length;
  const attentionMix = [
    { name: "High", value: highAttention },
    { name: "Medium", value: all.filter(q => q.attention === "medium").length },
    { name: "Low", value: all.filter(q => q.attention === "low" || !q.attention).length },
  ].filter(d => d.value > 0);
  const readinessBuckets = [
    { name: "0-25%", value: all.filter(q => (q.readiness_score || 0) <= 25).length },
    { name: "26-50%", value: all.filter(q => (q.readiness_score || 0) > 25 && (q.readiness_score || 0) <= 50).length },
    { name: "51-75%", value: all.filter(q => (q.readiness_score || 0) > 50 && (q.readiness_score || 0) <= 75).length },
    { name: "76-100%", value: all.filter(q => (q.readiness_score || 0) > 75).length },
  ].filter(d => d.value > 0);

  return (
    <Container fluid="xxl" className="py-4">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
        className="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-4">
        <div><span className="kicker">Officer Portal</span><h1 className="display-6 mb-0 mt-1">Review Queue</h1></div>
        <Button className="btn-mono btn-outline-mono" onClick={() => { setToken(null); setAuthed(false); }}>Sign out</Button>
      </motion.div>
      {msg && <div className="alert alert-success py-2" style={{ borderLeft: "4px solid #000" }}>{msg}</div>}
      {err && <div className="alert alert-danger py-2" style={{ borderLeft: "4px solid #ff3b30" }}>{err}</div>}
      <Row className="g-3 mb-4">
        <Col md={4} sm={6}><StatCard icon={ClipboardCheck} label="Assigned to you" value={totalAssigned} spark={[2,3,4,3,5,4]} /></Col>
        <Col md={4} sm={6}><StatCard icon={AlertTriangle} label="High attention" value={highAttention} spark={[0,1,0,2,1,1]} /></Col>
        <Col md={4} sm={6}><StatCard icon={Clock} label="SLA breached" value={slaBreached} spark={[0,0,1,0,1,0]} /></Col>
      </Row>
      <Row className="g-3 mb-4">
        <Col lg={4}>
          <div className="chart-card h-100">
            <span className="kicker">Queue mix</span>
            <h6 className="mt-1">Attention distribution</h6>
            <DonutChart data={attentionMix} height={190} />
            <div className="chart-note">Full queue — assigned + unassigned.</div>
          </div>
        </Col>
        <Col lg={8}>
          <div className="chart-card h-100">
            <span className="kicker">Readiness</span>
            <h6 className="mt-1">Queue readiness buckets</h6>
            <VerticalBars data={readinessBuckets} height={220} />
            <div className="chart-note">How submission-ready each application is before review.</div>
          </div>
        </Col>
      </Row>
      <Card className="stat-card mb-4"><Card.Body>
        <h5 className="fw-bold mb-3">Assigned to you</h5>
        {totalAssigned === 0 ? (
          <div className="text-center py-4" style={{ color: "#6d6d6d" }}><CheckCircle2 size={28} strokeWidth={1.2} className="mb-2" /><p style={{ fontSize: ".82rem" }}>Nothing assigned yet.</p></div>
        ) : (
          <div className="table-modern-wrap">
            <table className="table-modern">
              <thead>
                <tr>
                  <th>ID</th><th>Business</th><th>Approval</th><th>Readiness</th><th>Attention</th><th>SLA</th><th></th>
                </tr>
              </thead>
              <tbody>
                {queue?.assigned.map(entry => (
                  <tr key={entry.id} style={{ cursor: "pointer" }} onClick={() => setSelected(entry)}>
                    <td className="mono" style={{ fontSize: ".74rem" }}>{entry.id.slice(-8)}</td>
                    <td className="fw-bold">{entry.business_name}</td>
                    <td><span className="mono" style={{ fontSize: ".74rem" }}>{entry.approval_code}</span></td>
                    <td className="mono" style={{ fontSize: ".78rem" }}>{entry.readiness_score}%</td>
                    <td><AttentionTag level={entry.attention} /></td>
                    <td><SlaRing value={entry.sla?.remaining_hours ? Math.max(0, entry.sla.remaining_hours) / 720 : 1} size={40} strokeWidth={3} color={entry.sla?.state === "breached" ? "#ff3b30" : entry.sla?.state === "at_risk" ? "#ff9f0a" : "#000"} /></td>
                    <td className="text-end"><Button size="sm" className="btn-mono btn-outline-mono" style={{ padding: ".25rem .6rem", fontSize: ".68rem" }} onClick={(e) => { e.stopPropagation(); setSelected(entry); }}>Review</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card.Body></Card>
      <OfficerReviewPanel selected={selected} onClose={() => setSelected(null)} onReload={loadQueue} onMsg={setMsg} onErr={setErr} />
    </Container>
  );
}
