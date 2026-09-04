// @ts-nocheck
"use client";
import { useCallback, useEffect, useState } from "react";
import { Container, Row, Col, Card, Button, Form, ListGroup, Badge, ProgressBar } from "react-bootstrap";
import Link from "next/link";
import { motion } from "motion/react";
import {
  FileCheck2, RefreshCw, Sparkles, Send, CheckCircle2, Clock,
  Workflow, ScrollText, Inbox, PlusCircle, Upload,
  FileDown, BadgeCheck, Zap, Fingerprint,
} from "lucide-react";
import {
  getToken, setToken, getMyProfile, saveProfile,
  listApplications, createApplication, submitApplication,
  raiseGrievance, getSchemeRecommendations, askRegulatoryQuestion, getReadiness,
  startDigiLocker, verifyDigiLocker, applyDigiLocker, digiLockerStatus,
  generateForm, submitWithForm, downloadFormPdf,
} from "@/lib/api";
import NextDynamic from "next/dynamic";
import SlaRing from "@/components/ui/SlaRing";
import type { Checklist, ChecklistApproval } from "@/lib/api";

export const dynamic = "force-dynamic";

const StatCard = NextDynamic(() => import("@/components/ui/StatCard"), { ssr: false });
const GaugeChart = NextDynamic(() => import("@/components/ui/GaugeChart"), { ssr: false });
const ApprovalDag = NextDynamic(() => import("@/components/workflow/ApprovalDag"), { ssr: false });
const DonutChart = NextDynamic(() => import("@/components/ui/charts").then(m => m.DonutChart), { ssr: false });
const HorizontalBars = NextDynamic(() => import("@/components/ui/charts").then(m => m.HorizontalBars), { ssr: false });

type AppRow = {
  id: string; status: string; approval_name: string; approval_code: string;
  department: string; sla_days: number; readiness_score: number;
  sla: { state: string; remaining_hours: number | null }; green_channel: boolean;
  provisional_certificate: any; documents?: any[];
};

const TABS = ["Overview", "Checklist", "Applications", "Documents", "Ask AI", "Schemes"] as const;
/* placeholder */
export default function ApplicantPortal() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const [profile, setProfile] = useState<any>(null);
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [aiSummary, setAiSummary] = useState<any>(null);
  const [apps, setApps] = useState<AppRow[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const loadAll = useCallback(async () => {
    try {
      const me = await getMyProfile();
      setProfile(me.profile);
      setChecklist(me.checklist);
      setAiSummary(me.ai_summary);
      const list = await listApplications();
      setApps(list.applications || []);
      setAuthed(true);
    } catch { setAuthed(false); }
  }, []);

  useEffect(() => { setAuthed(getToken() ? null : false); }, []);
  useEffect(() => { if (authed === null) loadAll(); }, [authed, loadAll]);

  if (authed === false)
    return (
      <Container fluid="xxl" className="py-5">
        <Card className="mx-auto" style={{ maxWidth: 480 }}>
          <Card.Body className="p-4 text-center">
            <Inbox size={32} strokeWidth={1.5} className="mb-3" />
            <h2 className="display-7 mb-2">Applicant Portal</h2>
            <p style={{ color: "#6d6d6d" }}>Please <Link href="/login">sign in</Link> or{" "}
              <Link href="/register">register</Link> to continue.</p>
          </Card.Body>
        </Card>
      </Container>
    );

  const approved = apps.filter(a => a.status === "approved" || a.status === "provisionally_cleared").length;
  const pending = apps.filter(a => !["approved", "rejected", "provisionally_cleared"].includes(a.status)).length;
  const renewals = apps.filter(a => a.status === "approved").length;
  const avgReadiness = apps.length > 0
    ? Math.round(apps.reduce((s, a) => s + (a.readiness_score || 0), 0) / apps.length) : 0;

  return (
    <Container fluid="xxl" className="py-4">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-4">
        <div>
          <span className="kicker">Applicant Portal</span>
          <h1 className="display-6 mb-0 mt-1">{profile ? profile.name : "Loading…"}</h1>
        </div>
        <div className="d-flex gap-2">
          <Link href="/applicant/upload" className="btn btn-mono">
            <Upload size={14} strokeWidth={2} /> Upload
          </Link>
          <Button className="btn-mono btn-outline-mono"
            onClick={() => { setToken(null); setAuthed(false); setProfile(null); }}>
            Sign out
          </Button>
        </div>
      </motion.div>
      <div className="ir-tabs mb-4">
        {TABS.map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {msg && <div className="alert alert-success py-2" style={{ borderLeft: "4px solid #000" }}>{msg}</div>}
      {err && <div className="alert alert-danger py-2" style={{ borderLeft: "4px solid #ff3b30" }}>{err}</div>}
      {tab === "Overview" && <OverviewTab apps={apps} checklist={checklist} avgReadiness={avgReadiness} approved={approved} pending={pending} renewals={renewals} />}
      {tab === "Overview" && <KycCard />}
      {tab === "Checklist" && <ChecklistTab checklist={checklist} aiSummary={aiSummary} />}
      {tab === "Applications" && <ApplicationsTab apps={apps} reload={loadAll} setMsg={setMsg} setErr={setErr} />}
      {tab === "Documents" && <DocumentsTab />}
      {tab === "Ask AI" && <QaTab />}
      {tab === "Schemes" && <SchemesTab />}
    </Container>
  );
}
    function OverviewTab({ apps, checklist, avgReadiness, approved, pending, renewals }: any) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Row className="g-3 mb-4">
        <Col md={3} sm={6}><StatCard icon={FileCheck2} label="Applications" value={apps.length} spark={[2,3,3,4,5,6,6]} /></Col>
        <Col md={3} sm={6}><StatCard icon={CheckCircle2} label="Approved" value={approved} spark={[0,1,1,2,2,3,3]} /></Col>
        <Col md={3} sm={6}><StatCard icon={Clock} label="Pending" value={pending} spark={[3,4,4,3,5,4,4]} /></Col>
        <Col md={3} sm={6}><StatCard icon={RefreshCw} label="Renewals due" value={renewals} spark={[1,1,2,2,1,2,2]} /></Col>
      </Row>
      {/* Analytics: status mix + readiness by approval */}
      <Row className="g-3 mb-4">
        <Col lg={4}>
          <div className="chart-card h-100">
            <span className="kicker">Portfolio mix</span>
            <h6 className="mt-1">Applications by status</h6>
            <DonutChart data={[
              { name: "Approved", value: approved },
              { name: "Pending", value: pending },
              { name: "Renewals", value: renewals },
            ].filter(d => d.value > 0)} height={190} />
            <div className="chart-note">Deterministic counts — no estimation.</div>
          </div>
        </Col>
        <Col lg={8}>
          <div className="chart-card h-100">
            <span className="kicker">Readiness</span>
            <h6 className="mt-1">Score by approval</h6>
            <HorizontalBars
              data={apps.slice(0, 8).map((a: AppRow) => ({
                name: a.approval_code, value: a.readiness_score || 0,
              }))}
              height={220} />
            <div className="chart-note">0–100 readiness, computed from uploaded document checks.</div>
          </div>
        </Col>
      </Row>
      <Row className="g-3">
        <Col lg={5}>
          <Card className="stat-card h-100">
            <Card.Body className="d-flex flex-column align-items-center text-center gap-3 py-4">
              <span className="kicker">Readiness Score</span>
              <GaugeChart value={avgReadiness} size={200} strokeWidth={12} />
              <ListGroup variant="flush" className="w-100 text-start">
                {apps.filter((a: AppRow) => (a.readiness_score || 0) < 80).slice(0, 4).map((a: AppRow) => (
                  <ListGroup.Item key={a.id} className="px-0 d-flex justify-content-between" style={{ borderBottom: "1px solid #ecece8" }}>
                    <span className="mono" style={{ fontSize: ".72rem" }}>{a.approval_code}</span>
                    <span style={{ fontSize: ".72rem", color: "#6d6d6d" }}>−{100 - (a.readiness_score || 0)}</span>
                  </ListGroup.Item>
                ))}
              </ListGroup>
            </Card.Body>
          </Card>
        </Col>
        <Col lg={7}>
          <Card className="stat-card h-100"><Card.Body>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <div><span className="kicker">Approval Journey</span><h4 className="fw-bolder mb-0 mt-1">DAG workflow</h4></div>
              {checklist && <Badge className="mono" style={{ background: "#f6f6f4", color: "#000", border: "1.5px solid #000" }}>{checklist.approvals.length}</Badge>}
            </div>
            {checklist && checklist.approvals.length > 0 ? (
              <ApprovalDag checklist={checklist} statusOf={(a: ChecklistApproval) => {
                const app = apps.find((x: AppRow) => x.approval_id === a.id);
                if (!app) return "pending";
                return app.status === "approved" || app.status === "provisionally_cleared" ? "approved" : "pending";
              }} />
            ) : (
              <div className="text-center py-5" style={{ color: "#6d6d6d" }}><Workflow size={32} strokeWidth={1.2} className="mb-2" /><p style={{ fontSize: ".82rem" }}>Save your checklist to see the DAG.</p></div>
            )}
          </Card.Body></Card>
        </Col>
      </Row>
    </motion.div>
  );
}

function DocumentsTab() {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <div className="text-center py-5">
        <Upload size={40} strokeWidth={1.2} className="mb-3" />
        <h3 className="fw-bolder mb-2">Document Upload & Pre-Validation</h3>
        <p style={{ color: "#6d6d6d", maxWidth: 440, margin: "0 auto 1.5rem" }}>Upload documents for any application. Pre-validated against deterministic rules.</p>
        <Link href="/applicant/upload" className="btn btn-mono"><Upload size={14} strokeWidth={2} /> Go to Upload Centre</Link>
      </div>
    </motion.div>
  );
}
function ChecklistTab({ checklist, aiSummary }: { checklist: Checklist | null; aiSummary: any }) {
  if (!checklist || !checklist.known) return (
    <Card><Card.Body className="text-center py-5" style={{ color: "#6d6d6d" }}>
      <ScrollText size={32} strokeWidth={1.2} className="mb-2" /><p>Save your business profile to generate a personalised checklist.</p>
    </Card.Body></Card>
  );
  return (
    <Row className="g-3">
      <Col lg={8}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Personalised Checklist</span>
          <h4 className="fw-bolder mb-1 mt-1">{checklist.approvals.length} approvals required · {checklist.max_sla_days} day max SLA</h4>
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
                  <motion.tr key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: i * 0.05, ease: "easeOut" }}>
                    <td>
                      <div className="fw-bold">{a.name} {a.green_channel_eligible && <Badge style={{ background: "#000", color: "#fff", fontSize: ".62rem", padding: "2px 6px", borderRadius: 3 }}>GREEN</Badge>}</div>
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
        </Card.Body></Card>
      </Col>
      <Col lg={4}>
        {aiSummary && (
          <Card className="stat-card ai-summary-card"><Card.Body>
            <span className="kicker" style={{ color: "#8f8f8f" }}>AI summary</span>
            <h5 className="fw-bold mb-2 mt-1">How to think about this</h5>
            <p style={{ fontSize: ".82rem", color: "#c9c9c4" }}>{aiSummary.text}</p>
            <div className="principle-bar mt-3"><strong>Advisory only</strong> — rules decided this checklist, AI explains it.</div>
          </Card.Body></Card>
        )}
      </Col>
    </Row>
  );
}
function ApplicationsTab({ apps, reload, setMsg, setErr }: { apps: AppRow[]; reload: () => void; setMsg: (s: string) => void; setErr: (s: string) => void }) {
  const [appId, setAppId] = useState("");
  const [busyId, setBusyId] = useState("");
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
  async function genForm(id: string) {
    setBusyId(id); setErr(""); setMsg("");
    try {
      const meta = await generateForm(id);
      await downloadFormPdf(id);
      setMsg(`Unified Application Form generated and downloaded (verify code ${meta.verification_code}${meta.kyc_bound ? ", e-KYC bound" : ""}).`);
    } catch (e: any) { setErr(e.message); }
    finally { setBusyId(""); }
  }
  async function submitForm(id: string) {
    setBusyId(id); setErr(""); setMsg("");
    try {
      const res = await submitWithForm(id);
      setMsg(`Form ${res.form_verification_code} submitted — instantly dispatched to the officer portal.`);
      reload();
    } catch (e: any) { setErr(e.message); }
    finally { setBusyId(""); }
  }
  async function dlForm(id: string) {
    setErr(""); setMsg("");
    try { await downloadFormPdf(id); setMsg("Form PDF downloaded."); }
    catch (e: any) { setErr(e.message); }
  }
  return (
    <Row className="g-3">
      <Col lg={8}>
        <Card className="stat-card"><Card.Body>
          <h5 className="fw-bold mb-3">Your Applications</h5>
          {apps.length === 0 ? (
            <div className="text-center py-4" style={{ color: "#6d6d6d" }}><FileCheck2 size={28} strokeWidth={1.2} className="mb-2" /><p style={{ fontSize: ".82rem" }}>No applications yet.</p></div>
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
                      <td><Badge style={{ background: "transparent", color: "#000", border: "1.5px solid #000", borderRadius: 3, fontSize: ".64rem", fontWeight: 700, letterSpacing: ".08em" }}>{a.status.replace(/_/g, " ").toUpperCase()}</Badge></td>
                      <td>
                        <div className="d-flex align-items-center gap-2">
                          <ProgressBar now={a.readiness_score || 0} style={{ flex: 1, height: 4, borderRadius: 0, background: "#e7e7e2" }} />
                          <span className="mono" style={{ fontSize: ".72rem" }}>{a.readiness_score || 0}%</span>
                        </div>
                      </td>
                      <td><SlaRing value={a.sla?.remaining_hours ? Math.max(0, a.sla.remaining_hours) / (a.sla_days * 24) : 1} size={38} strokeWidth={3} color={a.sla?.state === "breached" ? "#ff3b30" : a.sla?.state === "at_risk" ? "#ff9f0a" : "#000"} /></td>
                      <td className="text-end">
                        {a.status === "draft" && <span className="d-inline-flex gap-1 flex-wrap">
                          <Button size="sm" className="btn-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }} disabled={busyId === a.id} onClick={() => genForm(a.id)}><FileDown size={12} /> {busyId === a.id ? "…" : "Auto-Form PDF"}</Button>
                          <Button size="sm" className="btn-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }} disabled={busyId === a.id} onClick={() => submitForm(a.id)}><Zap size={12} /> Submit Form</Button>
                          <Link href={`/applicant/upload?app=${a.id}`}><Button size="sm" className="btn-mono btn-outline-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }}>Docs</Button></Link>
                        </span>}
                        {a.status !== "draft" && <Button size="sm" className="btn-mono btn-outline-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }} onClick={() => dlForm(a.id)}><FileDown size={12} /> Form PDF</Button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card.Body></Card>
      </Col>
      <Col lg={4}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Quick create</span>
          <h5 className="fw-bold mb-2 mt-1">New application</h5>
          <Form.Group className="mb-3">
            <Form.Label style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", fontWeight: 700 }}>Checklist approval ID</Form.Label>
            <Form.Control value={appId} onChange={e => setAppId(e.target.value)} placeholder="approval-uuid-here" className="mono" style={{ fontSize: ".82rem" }} />
          </Form.Group>
          <Button className="btn-mono w-100" disabled={!appId} onClick={() => apply(appId)}><PlusCircle size={14} strokeWidth={2} /> Create</Button>
          <div className="principle-bar mt-3"><strong>Tip:</strong> Copy the approval ID from your checklist.</div>
        </Card.Body></Card>
      </Col>
    </Row>
  );
}
function QaTab() {
  const [q, setQ] = useState("What approvals do I need for a food processing factory?");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  async function ask() {
    setBusy(true);
    try { setRes(await askRegulatoryQuestion(q)); }
    finally { setBusy(false); }
  }
  return (
    <Card className="stat-card"><Card.Body>
      <span className="kicker">Regulatory Q&A</span>
      <h4 className="fw-bolder mb-1 mt-1">Ask · RAG-grounded · Cites sources</h4>
      <p style={{ color: "#6d6d6d", fontSize: ".82rem" }}>Answers are generated from the regulatory knowledge base. Always advisory.</p>
      <div className="d-flex gap-2 mt-3">
        <Form.Control value={q} onChange={e => setQ(e.target.value)} placeholder="Ask a regulatory question…" />
        <Button className="btn-mono flex-shrink-0" onClick={ask} disabled={busy}>
          {busy ? "Thinking…" : <><Send size={14} strokeWidth={2} /> Ask</>}
        </Button>
      </div>
      {res && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="mt-4 p-3" style={{ background: "#f6f6f4", borderRadius: 6, borderLeft: "4px solid #000" }}>
          <p className="mb-2" style={{ fontSize: ".88rem" }}>{res.answer}</p>
          {res.citations?.length > 0 && (
            <div style={{ fontSize: ".72rem", color: "#6d6d6d" }}>Sources: {res.citations.map((c: any) => c.source).join(" · ")}</div>
          )}
        </motion.div>
      )}
    </Card.Body></Card>
  );
}

function SchemesTab() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { getSchemeRecommendations().then(setData).catch(() => {}); }, []);
  if (!data) return (
    <Card><Card.Body className="text-center py-5" style={{ color: "#6d6d6d" }}>
      <Sparkles size={28} strokeWidth={1.2} className="mb-2" /><p>Save your profile to see scheme recommendations.</p>
    </Card.Body></Card>
  );
  return (
    <Row className="g-3">
      <Col lg={8}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Eligible Schemes</span>
          <h4 className="fw-bolder mb-3 mt-1">{data.eligible.length} matches for your profile</h4>
          <ListGroup variant="flush">
            {data.eligible.map((s: any) => (
              <ListGroup.Item key={s.id} className="px-0 py-3" style={{ borderBottom: "1px solid #ecece8" }}>
                <div className="d-flex align-items-start gap-2">
                  <CheckCircle2 size={16} strokeWidth={2} style={{ color: "#000", marginTop: 2 }} />
                  <div>
                    <div className="fw-bold">{s.name}</div>
                    <div style={{ color: "#6d6d6d", fontSize: ".78rem" }}>{s.description}</div>
                    <div style={{ fontSize: ".74rem", color: "#000", fontWeight: 600 }}>{s.benefits}</div>
                  </div>
                </div>
              </ListGroup.Item>
            ))}
            {data.eligible.length === 0 && (
              <ListGroup.Item className="px-0 text-center py-4" style={{ color: "#6d6d6d" }}>No eligible schemes yet.</ListGroup.Item>
            )}
          </ListGroup>
        </Card.Body></Card>
      </Col>
      <Col lg={4}>
        <Card className="stat-card"><Card.Body>
          <h5 className="fw-bold mb-2">Not yet eligible</h5>
          <ListGroup variant="flush">
            {data.others.slice(0, 5).map((s: any) => (
              <ListGroup.Item key={s.id} className="px-0 py-2" style={{ borderBottom: "1px solid #ecece8", fontSize: ".78rem" }}>
                <div className="fw-bold">{s.name}</div>
                <div style={{ color: "#6d6d6d", fontSize: ".72rem" }}>{s.explanation}</div>
              </ListGroup.Item>
            ))}
          </ListGroup>
          <div className="principle-bar mt-3"><strong>Rule-based only</strong> — advisory, not a scheme guarantee.</div>
        </Card.Body></Card>
            </Col>
    </Row>
  );
}

function KycCard() {
  const [status, setStatus] = useState<any>(null);
  const [step, setStep] = useState<"idle" | "otp" | "consent">("idle");
  const [aadhaar, setAadhaar] = useState("");
  const [otp, setOtp] = useState("");
  const [consentId, setConsentId] = useState("");
  const [demoOtp, setDemoOtp] = useState<string | null>(null);
  const [masked, setMasked] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { digiLockerStatus().then(setStatus).catch(() => {}); }, []);

  async function start() {
    setBusy(true); setErr(""); setMsg("");
    try {
      const res = await startDigiLocker(aadhaar.replace(/\s/g, ""));
      setConsentId(res.consent_id); setMasked(res.aadhaar_masked);
      setDemoOtp(res.demo_otp); setStep("otp");
      setMsg("OTP sent via DigiLocker gateway" + (res.demo_otp ? " (sandbox demo OTP shown below)." : "."));
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  async function verify() {
    setBusy(true); setErr(""); setMsg("");
    try {
      const res = await verifyDigiLocker(consentId, otp);
      setMsg(res.note || "Identity verified."); setStep("consent");
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  async function apply() {
    setBusy(true); setErr(""); setMsg("");
    try {
      const res = await applyDigiLocker(consentId, {});
      setMsg("e-KYC applied to your profile — name/PAN/GSTIN will be cross-checked automatically.");
      setStep("idle"); setOtp(""); setDemoOtp(null);
      const s = await digiLockerStatus(); setStatus(s);
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <Card className="stat-card"><Card.Body>
      <span className="kicker">DigiLocker e-KYC</span>
      <h5 className="fw-bold mb-2 mt-1">
        {status?.kyc_verified ? <><BadgeCheck size={18} strokeWidth={2} className="me-1" /> Identity verified</> : <><Fingerprint size={18} strokeWidth={2} className="me-1" /> Auto-fill via DigiLocker</>}
      </h5>
      {status?.kyc_verified ? (
        <>
          <div style={{ fontSize: ".8rem" }} className="mb-1"><strong>{status.identity?.name}</strong></div>
          <div style={{ fontSize: ".76rem", color: "#6d6d6d" }} className="mb-1">Aadhaar: {status.identity?.aadhaar_masked} · Ref: {status.identity?.digilocker_ref}</div>
          <div style={{ fontSize: ".76rem", color: "#6d6d6d" }} className="mb-2">Source: {status.identity?.kyc_source}</div>
          <div className="principle-bar"><strong>Verified identity</strong> — generated forms are bound to this e-KYC; full Aadhaar number is never stored.</div>
        </>
      ) : step === "idle" ? (
        <>
          <p style={{ fontSize: ".8rem", color: "#6d6d6d" }}>Authenticate with Aadhaar OTP to auto-fill your application form from verified government records — no manual typing, no typos.</p>
          <Form.Control className="mono mb-2" placeholder="12-digit Aadhaar number" value={aadhaar} onChange={(e: any) => setAadhaar(e.target.value)} maxLength={14} />
          <Button className="btn-mono w-100" disabled={aadhaar.replace(/\s/g, "").length !== 12 || busy} onClick={start}>
            <Fingerprint size={14} strokeWidth={2} /> {busy ? "Sending OTP…" : "Start e-KYC"}
          </Button>
        </>
      ) : step === "otp" ? (
        <>
          <p style={{ fontSize: ".8rem", color: "#6d6d6d" }}>Enter the OTP sent for {masked}.</p>
          {demoOtp && <div className="alert alert-warning py-2" style={{ fontSize: ".74rem" }}>Sandbox demo OTP: <strong className="mono">{demoOtp}</strong></div>}
          <Form.Control className="mono mb-2" placeholder="6-digit OTP" value={otp} onChange={(e: any) => setOtp(e.target.value)} maxLength={6} />
          <Button className="btn-mono w-100" disabled={otp.length < 4 || busy} onClick={verify}>{busy ? "Verifying…" : "Verify OTP"}</Button>
        </>
      ) : (
        <>
          <p style={{ fontSize: ".8rem", color: "#6d6d6d" }}>Verified. Apply this identity to your business profile now.</p>
          <Button className="btn-mono w-100" disabled={busy} onClick={apply}><BadgeCheck size={14} strokeWidth={2} /> {busy ? "Applying…" : "Apply to my profile"}</Button>
        </>
      )}
      {msg && <div className="alert alert-success py-2 mt-2" style={{ fontSize: ".74rem", borderLeft: "4px solid #000" }}>{msg}</div>}
      {err && <div className="alert alert-danger py-2 mt-2" style={{ fontSize: ".74rem", borderLeft: "4px solid #ff3b30" }}>{err}</div>}
    </Card.Body></Card>
  );
}
