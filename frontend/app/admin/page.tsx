// @ts-nocheck
"use client";
import { useCallback, useEffect, useState } from "react";
import { Container, Row, Col, Card, Button, Badge } from "react-bootstrap";
import { Shield, Activity, Zap, Timer, Scale } from "lucide-react";
import NextDynamic from "next/dynamic";
import {
  getToken, setToken, getAdminAnalytics, getAuditLog, toggleGreenChannel,
  getGreenChannelStatus, titleCase,
} from "@/lib/api";

const DonutChart = NextDynamic(() => import("@/components/ui/charts").then(m => m.DonutChart), { ssr: false });
const HorizontalBars = NextDynamic(() => import("@/components/ui/charts").then(m => m.HorizontalBars), { ssr: false });
const VerticalBars = NextDynamic(() => import("@/components/ui/charts").then(m => m.VerticalBars), { ssr: false });
const StatCard = NextDynamic(() => import("@/components/ui/StatCard"), { ssr: false });

export default function AdminDashboard() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [summary, setSummary] = useState<any>(null);
  const [audit, setAudit] = useState<any>(null);
  const [gc, setGc] = useState<boolean>(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      setErr("");
      const [s, a, g] = await Promise.all([
        getAdminAnalytics(), getAuditLog(100), getGreenChannelStatus(),
      ]);
      setSummary(s); setAudit(a); setGc(g.enabled); setAuthed(true);
    } catch (e: any) { setAuthed(false); setErr(e.message); }
  }, []);

  useEffect(() => { setAuthed(getToken() ? null : false); }, []);
  useEffect(() => { if (authed === null) load(); }, [authed, load]);

  const handleToggleGc = async () => {
    try {
      setMsg("");
      const r = await toggleGreenChannel(!gc);
      setGc(r.enabled);
      setMsg(r.enabled ? "Green Channel has been enabled." : "Green Channel has been disabled.");
    } catch (e: any) { setErr(e.message); }
  };

  if (authed === false) {
    return (
      <Container fluid="xxl" className="py-5">
        <Card className="mx-auto" style={{ maxWidth: 520 }}>
          <Card.Body className="p-4 text-center">
            <Shield size={32} strokeWidth={1.5} className="mb-3" />
            <h2 className="display-7 mb-2">Admin Dashboard</h2>
            <p style={{ color: "#6d6d6d" }}>Admin login required.</p>
            <a className="btn btn-mono mt-2" href="/login">Sign in</a>
          </Card.Body>
        </Card>
      </Container>
    );
  }

  const k = summary?.kpis || {};
  const byStatus = k.by_status || {};
  const inFlight = Object.entries(byStatus)
    .filter(([s]) => !["approved", "rejected", "provisionally_cleared"].includes(s))
    .reduce((a: any, [, n]) => a + (n as number), 0);

  const statusDonut = Object.entries(byStatus).map(([s, n]) => ({
    name: titleCase(s), value: n as number,
  })).filter((d: any) => d.value > 0);

  const bottleneckBars = (summary?.bottleneck_analytics || []).slice(0, 7).map((b: any) => ({
    name: b.department || b.code,
    value: b.applications || 0,
  }));

  const deficiencyBars = (summary?.deficiency_analytics || []).slice(0, 7).map((d: any) => ({
    name: d.check, value: d.count || 0,
  }));

  return (
    <Container fluid="xxl" className="py-4">
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-4">
        <div>
          <span className="kicker">Admin Portal</span>
          <h1 className="display-6 mb-0 mt-1">Control Room</h1>
        </div>
        <Button className="btn-mono btn-outline-mono" onClick={() => { setToken(null); setAuthed(false); }}>Sign out</Button>
      </div>

      {err && <div className="alert alert-danger py-2" style={{ borderLeft: "4px solid #ff3b30" }}>{err}</div>}
      {msg && <div className="alert alert-success py-2" style={{ borderLeft: "4px solid #000" }}>{msg}</div>}

      <Row className="g-3 mb-4">
        <Col md={3} sm={6}><StatCard icon={Activity} label="Total applications" value={k.total_applications || 0} spark={[2,3,4,5,6,7,8]} /></Col>
        <Col md={3} sm={6}><StatCard icon={Timer} label="SLA breached" value={k.sla_breached_active || 0} spark={[0,0,1,0,1,0,0]} /></Col>
        <Col md={3} sm={6}><StatCard icon={Zap} label="Green Channel" value={k.green_channel_certificates || 0} spark={[0,1,1,2,2,2,3]} /></Col>
        <Col md={3} sm={6}><StatCard icon={Scale} label="In-flight" value={inFlight} spark={[3,3,4,4,5,5,6]} /></Col>
      </Row>
      {/* Green Channel governance */}
      <Card className="stat-card mb-4"><Card.Body>
        <span className="kicker">Governance</span>
        <h5 className="fw-bold mb-3 mt-1">Green Channel</h5>
        <div className="d-flex align-items-center gap-3 flex-wrap">
          <Badge className="mono" style={{ background: gc ? "#000" : "transparent", color: gc ? "#fff" : "#000", border: "1.5px solid #000", fontSize: ".66rem", letterSpacing: ".1em", padding: "4px 10px" }}>
            {gc ? "ENABLED" : "DISABLED"}
          </Badge>
          <Button className="btn-mono btn-outline-mono" style={{ padding: ".5rem 1.1rem", fontSize: ".7rem" }} onClick={handleToggleGc}>
            {gc ? "Disable Green Channel" : "Enable Green Channel"}
          </Button>
          <span style={{ color: "#6d6d6d", fontSize: ".8rem" }}>
            {gc ? "Provisional clearance is currently available for 100%-pass whitelisted applications."
                : "Green Channel is disabled. All applications require full officer scrutiny."}
          </span>
        </div>
      </Card.Body></Card>

      {/* Analytics charts */}
      <Row className="g-3 mb-4">
        <Col lg={4}>
          <div className="chart-card h-100">
            <span className="kicker">Statewide</span>
            <h6 className="mt-1">Status distribution</h6>
            <DonutChart data={statusDonut} height={210} />
            <div className="chart-note">Every live application, by workflow status.</div>
          </div>
        </Col>
        <Col lg={4}>
          <div className="chart-card h-100">
            <span className="kicker">Bottlenecks</span>
            <h6 className="mt-1">Load by department</h6>
            <HorizontalBars data={bottleneckBars} height={210} />
            <div className="chart-note">Where applications pile up the most.</div>
          </div>
        </Col>
        <Col lg={4}>
          <div className="chart-card h-100">
            <span className="kicker">Deficiencies</span>
            <h6 className="mt-1">Top failing checks</h6>
            <VerticalBars data={deficiencyBars} height={210} />
            <div className="chart-note">Deterministic check failures, ranked.</div>
          </div>
        </Col>
      </Row>

      {/* Bottleneck + deficiency tables */}
      <Row className="g-3 mb-4">
        <Col lg={6}>
          <Card className="stat-card h-100"><Card.Body>
            <h5 className="fw-bold mb-3">Bottleneck Analytics</h5>
            <div className="table-modern-wrap">
              <table className="table-modern">
                <thead><tr><th>Department</th><th className="text-end">Applications</th><th className="text-end">Avg SLA (days)</th></tr></thead>
                <tbody>
                  {(summary?.bottleneck_analytics || []).map((b: any, i: number) => (
                    <tr key={i}>
                      <td>{b.department || b.code}</td>
                      <td className="text-end mono">{b.applications || 0}</td>
                      <td className="text-end mono">{b.avg_sla_days || 0}</td>
                    </tr>
                  ))}
                  {(!summary?.bottleneck_analytics || summary.bottleneck_analytics.length === 0) && (
                    <tr><td colSpan={3} style={{ padding: 16, color: "#6d6d6d", textAlign: "center" }}>No data yet</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card.Body></Card>
        </Col>
        <Col lg={6}>
          <Card className="stat-card h-100"><Card.Body>
            <h5 className="fw-bold mb-3">Deficiency Analytics</h5>
            <div className="table-modern-wrap">
              <table className="table-modern">
                <thead><tr><th>Failing Check</th><th className="text-end">Count</th></tr></thead>
                <tbody>
                  {(summary?.deficiency_analytics || []).map((d: any, i: number) => (
                    <tr key={i}>
                      <td>{d.check}</td>
                      <td className="text-end mono">{d.count}</td>
                    </tr>
                  ))}
                  {(!summary?.deficiency_analytics || summary.deficiency_analytics.length === 0) && (
                    <tr><td colSpan={2} style={{ padding: 16, color: "#6d6d6d", textAlign: "center" }}>No data yet</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card.Body></Card>
        </Col>
      </Row>

      {/* Audit trail */}
      <Card className="stat-card mb-4"><Card.Body>
        <span className="kicker">Traceability</span>
        <h5 className="fw-bold mb-3 mt-1">Immutable Audit Trail</h5>
        <div style={{ maxHeight: 400, overflowY: "auto" }}>
          <div className="table-modern-wrap">
            <table className="table-modern">
              <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Source</th></tr></thead>
              <tbody>
                {(audit?.entries || []).map((e: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontSize: 13 }} className="mono">{new Date(e.timestamp).toLocaleString()}</td>
                    <td>{e.actor}</td>
                    <td>{e.action}</td>
                    <td>
                      <Badge className="mono" style={{ background: e.decision_source === "system" ? "#fff" : "#000", color: e.decision_source === "system" ? "#000" : "#fff", border: "1.5px solid #000", fontSize: 10.5, letterSpacing: ".08em" }}>
                        {e.decision_source || "human"}
                      </Badge>
                    </td>
                  </tr>
                ))}
                {(!audit?.entries || audit.entries.length === 0) && (
                  <tr><td colSpan={4} style={{ padding: 16, color: "#6d6d6d", textAlign: "center" }}>No audit entries yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </Card.Body></Card>
    </Container>
  );
}