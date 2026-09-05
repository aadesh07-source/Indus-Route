// @ts-nocheck
"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Container, Row, Col, Card, Button, Form, ListGroup, Badge, ProgressBar, Alert } from "react-bootstrap";
import Link from "next/link";
import { motion } from "motion/react";
import {
  FileCheck2, RefreshCw, Sparkles, Send, CheckCircle2, Clock,
  Workflow, ScrollText, Inbox, PlusCircle, Upload,
  FileDown, BadgeCheck, Zap, Fingerprint,
  Shield, ArrowRight, AlertTriangle, FileText, Download,
} from "lucide-react";
import {
  getToken, setToken, getMyProfile, saveProfile,
  listApplications, createApplication, submitApplication,
  raiseGrievance, getSchemeRecommendations, askRegulatoryQuestion, getReadiness,
  startDigiLocker, verifyDigiLocker, applyDigiLocker, digiLockerStatus,
  generateForm, submitWithForm, downloadFormPdf, resubmitApplication,
  updateSelectedSchemes, autoFillFromData, downloadCertificatePdf,
} from "@/lib/api";
import NextDynamic from "next/dynamic";
import SlaRing from "@/components/ui/SlaRing";
import ChecklistLivePanel from "./ChecklistTab";
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
  sla: { state: string; remaining_hours: number | null; deadline: string | null };
  green_channel: boolean;
  provisional_certificate: any; documents?: any[];
  docs_pending?: boolean; docs_passed?: number; docs_total?: number; docs_count?: number;
  feedback?: string; certificate?: any; selected_schemes?: string[];
};

const TABS = ["Overview", "DigiLocker KYC", "Schemes", "Documents Required", "Application", "Ask AI"] as const;

export default function ApplicantPortal() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const [profile, setProfile] = useState<any>(null);
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [aiSummary, setAiSummary] = useState<any>(null);
  const [apps, setApps] = useState<AppRow[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [activeAppId, setActiveAppId] = useState<string>("");

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

      <div className="d-flex flex-wrap gap-2 mb-3" style={{ fontSize: ".72rem" }}>
        <span className="badge border text-dark" style={{ background: "#f6f6f4" }}>
          Step 1 · Overview
        </span>
        <ArrowRight size={14} className="align-self-center" />
        <span className="badge border text-dark" style={{ background: "#f6f6f4" }}>
          Step 2 · DigiLocker KYC
        </span>
        <ArrowRight size={14} className="align-self-center" />
        <span className="badge border text-dark" style={{ background: "#f6f6f4" }}>
          Step 3 · Schemes
        </span>
        <ArrowRight size={14} className="align-self-center" />
        <span className="badge border text-dark" style={{ background: "#f6f6f4" }}>
          Step 4 · Documents Required
        </span>
        <ArrowRight size={14} className="align-self-center" />
        <span className="badge border text-dark" style={{ background: "#000", color: "#fff" }}>
          Step 5 · Application
        </span>
      </div>

      <div className="ir-tabs mb-4">
        {TABS.map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {msg && <div className="alert alert-success py-2" style={{ borderLeft: "4px solid #000" }}>{msg}</div>}
      {err && <div className="alert alert-danger py-2" style={{ borderLeft: "4px solid #ff3b30" }}>{err}</div>}

      {tab === "Overview" && (
        <OverviewTab apps={apps} checklist={checklist} avgReadiness={avgReadiness}
          approved={approved} pending={pending} renewals={renewals} />
      )}
      {tab === "DigiLocker KYC" && <KycCard setMsg={setMsg} setErr={setErr} />}
      {tab === "Schemes" && (
        <SchemesTab
          activeAppId={activeAppId}
          apps={apps}
          setMsg={setMsg}
          setErr={setErr}
          onSaved={(appId) => { setActiveAppId(appId); loadAll(); }}
        />
      )}
      {tab === "Documents Required" && (
        <DocumentsRequiredTab checklist={checklist} apps={apps} />
      )}
      {tab === "Application" && (
        <ApplicationsTab
          apps={apps}
          checklist={checklist}
          reload={loadAll}
          setMsg={setMsg}
          setErr={setErr}
          onPickApp={(id) => setActiveAppId(id)}
        />
      )}
      {tab === "Ask AI" && <QaTab />}
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
      <Row className="g-3">
        <Col lg={12}>
          <ChecklistLivePanel checklist={checklist} apps={apps} />
        </Col>
      </Row>
    </motion.div>
  );
}

function DocumentsRequiredTab({ checklist, apps }: { checklist: Checklist | null; apps: AppRow[] }) {
  if (!checklist || !checklist.known) {
    return (
      <Card><Card.Body className="text-center py-5" style={{ color: "#6d6d6d" }}>
        <ScrollText size={32} strokeWidth={1.2} className="mb-2" /><p>Save your business profile to generate the personalised document list.</p>
      </Card.Body></Card>
    );
  }
  const requiredSet = new Map<string, { doc: string; fromApprovals: string[] }>();
  for (const a of checklist.approvals) {
    for (const d of a.required_documents || []) {
      if (!requiredSet.has(d)) requiredSet.set(d, { doc: d, fromApprovals: [] });
      requiredSet.get(d)!.fromApprovals.push(a.code);
    }
  }
  const required = Array.from(requiredSet.values());

  return (
    <Row className="g-3">
      <Col lg={8}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Step 4 · Documents Required</span>
          <h4 className="fw-bolder mb-1 mt-1">Personalised for your sector — {required.length} unique documents</h4>
          <p style={{ color: "#6d6d6d", fontSize: ".82rem" }}>
            Upload each document once via the Upload Centre. The deterministic engine will
            re-run all statutory checks (PAN/GSTIN link, OCR, regex, name similarity) on
            every submission.
          </p>
          <div className="table-modern-wrap mt-3">
            <table className="table-modern">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Required by</th>
                  <th className="text-end">Status</th>
                </tr>
              </thead>
              <tbody>
                {required.map((r, i) => (
                  <tr key={r.doc}>
                    <td><span className="fw-bold">{r.doc.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</span></td>
                    <td className="mono" style={{ fontSize: ".72rem" }}>{r.fromApprovals.join(", ")}</td>
                    <td className="text-end">
                      <Badge style={{ background: "transparent", color: "#000", border: "1.5px solid #000", borderRadius: 3, fontSize: ".62rem", fontWeight: 700, letterSpacing: ".08em" }}>
                        REQUIRED
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card.Body></Card>
      </Col>
      <Col lg={4}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Quick access</span>
          <h5 className="fw-bold mb-2 mt-1">Open Upload Centre</h5>
          <p style={{ color: "#6d6d6d", fontSize: ".82rem" }}>Drop-zone, OCR + 12 deterministic checks run per file.</p>
          <Link href="/applicant/upload" className="btn btn-mono w-100">
            <Upload size={14} strokeWidth={2} /> Go to Upload Centre
          </Link>
          <div className="principle-bar mt-3">
            <strong>Reusable</strong> — same document is linked to every application that needs it.
          </div>
        </Card.Body></Card>
      </Col>
    </Row>
  );
}

function KycCard({ setMsg, setErr }: { setMsg: (s: string) => void; setErr: (s: string) => void }) {
  const [status, setStatus] = useState<any>(null);
  const [step, setStep] = useState<"idle" | "otp" | "consent">("idle");
  const [aadhaar, setAadhaar] = useState("");
  const [otp, setOtp] = useState("");
  const [consentId, setConsentId] = useState("");
  const [demoOtp, setDemoOtp] = useState<string | null>(null);
  const [masked, setMasked] = useState("");
  const [busy, setBusy] = useState(false);

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
    <Row className="g-3">
      <Col lg={8}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Step 2 · DigiLocker e-KYC</span>
          <h4 className="fw-bolder mb-1 mt-1">
            {status?.kyc_verified ? <><BadgeCheck size={20} strokeWidth={2} className="me-1" /> Identity verified</> : <><Fingerprint size={20} strokeWidth={2} className="me-1" /> Auto-fill via DigiLocker</>}
          </h4>
          <p style={{ color: "#6d6d6d", fontSize: ".82rem" }}>
            Aadhaar OTP authentication pulls verified PAN, GSTIN and address from government records.
            Generated application forms become e-KYC bound (tamper-evident).
          </p>
          {status?.kyc_verified ? (
            <>
              <div style={{ fontSize: ".84rem" }} className="mb-1"><strong>{status.identity?.name}</strong></div>
              <div style={{ fontSize: ".76rem", color: "#6d6d6d" }} className="mb-1">Aadhaar: {status.identity?.aadhaar_masked} · Ref: {status.identity?.digilocker_ref}</div>
              <div style={{ fontSize: ".76rem", color: "#6d6d6d" }} className="mb-2">Source: {status.identity?.kyc_source} · Verified at: {status.identity?.verified_at}</div>
              <div className="principle-bar"><strong>Verified identity</strong> — full Aadhaar is never stored.</div>
            </>
          ) : step === "idle" ? (
            <>
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
        </Card.Body></Card>
      </Col>
      <Col lg={4}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Why KYC?</span>
          <ListGroup variant="flush" style={{ fontSize: ".82rem" }}>
            <ListGroup.Item className="px-0 py-2" style={{ borderBottom: "1px solid #ecece8" }}>
              <strong>No manual typing.</strong> Name/PAN/GSTIN pulled from verified records.
            </ListGroup.Item>
            <ListGroup.Item className="px-0 py-2" style={{ borderBottom: "1px solid #ecece8" }}>
              <strong>Cross-checked.</strong> Documents you upload are matched against the verified bundle.
            </ListGroup.Item>
            <ListGroup.Item className="px-0 py-2" style={{ borderBottom: "1px solid #ecece8" }}>
              <strong>Privacy.</strong> Only the last-4 of Aadhaar + a consent reference are stored.
            </ListGroup.Item>
            <ListGroup.Item className="px-0 py-2">
              <strong>Tamper-evident.</strong> PDF forms are hash-bound to this verified identity.
            </ListGroup.Item>
          </ListGroup>
        </Card.Body></Card>
      </Col>
    </Row>
  );
}

function SchemesTab({ activeAppId, apps, setMsg, setErr, onSaved }: {
  activeAppId: string; apps: AppRow[];
  setMsg: (s: string) => void; setErr: (s: string) => void;
  onSaved: (appId: string) => void;
}) {
  const [data, setData] = useState<any>(null);
  const [pickedAppId, setPickedAppId] = useState<string>(activeAppId || "");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string>("");
  const editableApps = apps.filter(a =>
    ["draft", "clarification_pending", "returned"].includes(a.status));

  useEffect(() => { getSchemeRecommendations().then(setData).catch(() => {}); }, []);

  useEffect(() => {
    if (!pickedAppId && editableApps[0]) setPickedAppId(editableApps[0].id);
  }, [editableApps, pickedAppId]);

  // Selection works with or without an application: if an application exists
  // it is attached instantly; otherwise it is saved locally and auto-attached
  // the moment an application is created.
  useEffect(() => {
    const cur = apps.find(a => a.id === pickedAppId);
    const saved: string[] = JSON.parse(localStorage.getItem("indus_scheme_pick") || "[]");
    if (cur) {
      const merged = Array.from(new Set([...(cur.selected_schemes || []), ...saved]));
      setSelected(new Set(merged));
      if (saved.length) {
        updateSelectedSchemes(pickedAppId, merged).then(() => {
          localStorage.removeItem("indus_scheme_pick");
          setMsg("Your saved scheme selection was attached to this application.");
          onSaved(pickedAppId);
        }).catch(() => {});
      }
    } else if (saved.length) setSelected(new Set(saved));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickedAppId]);

  async function toggle(id: string) {
    const n = new Set(selected);
    if (n.has(id)) n.delete(id); else n.add(id);
    setSelected(n);
    if (pickedAppId) {
      try {
        const r = await updateSelectedSchemes(pickedAppId, Array.from(n));
        setMsg(`${r.count} scheme(s) attached to your application — they appear in the auto-filled form.`);
        onSaved(pickedAppId);
      } catch (e: any) { setErr(e.message); }
    } else {
      localStorage.setItem("indus_scheme_pick", JSON.stringify(Array.from(n)));
      setMsg(`${n.size} scheme(s) selected — they attach automatically when you create your application.`);
    }
  }

  if (!data) return (
    <Card><Card.Body className="text-center py-5" style={{ color: "#6d6d6d" }}>
      <Sparkles size={28} strokeWidth={1.2} className="mb-2" /><p>Save your profile to see scheme recommendations.</p>
    </Card.Body></Card>
  );

  const groups: Record<string, any[]> = {};
  for (const s of data.eligible) {
    const key = s.category || "Schemes";
    (groups[key] = groups[key] || []).push(s);
  }

  return (
    <Row className="g-3">
      <Col lg={8}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Schemes · select what you want to apply for</span>
          <h4 className="fw-bolder mb-3 mt-1">{data.eligible.length} eligible schemes · grouped by sector package</h4>
          {editableApps.length > 1 && (
            <Form.Group className="mb-3">
              <Form.Label style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", fontWeight: 700 }}>
                Attach schemes to which application?
              </Form.Label>
              <Form.Select value={pickedAppId} onChange={(e) => setPickedAppId(e.target.value)}>
                {editableApps.map(a => (
                  <option key={a.id} value={a.id}>
                    {a.approval_code} — {a.id.slice(-8)} ({a.status.replace(/_/g, " ")})
                  </option>
                ))}
              </Form.Select>
            </Form.Group>
          )}
          {Object.entries(groups).map(([cat, list]) => (
            <div key={cat} className="mb-3">
              <div className="kicker" style={{ marginBottom: 4 }}>{cat}</div>
              <ListGroup variant="flush">
                {list.map((s: any) => {
                  const ticked = selected.has(s.id);
                  const open = expanded === s.id;
                  return (
                    <ListGroup.Item key={s.id} className="px-0 py-3" style={{ borderBottom: "1px solid #ecece8" }}>
                      <div className="d-flex align-items-start gap-2">
                        <Button
                          size="sm"
                          className={ticked ? "btn-mono" : "btn-mono btn-outline-mono"}
                          style={{ minWidth: 92, padding: ".3rem .8rem", fontSize: ".7rem", flexShrink: 0 }}
                          onClick={() => toggle(s.id)}
                        >
                          {ticked ? <><CheckCircle2 size={12} /> Selected</> : <>Select</>}
                        </Button>
                        <div className="flex-grow-1">
                          <div className="d-flex justify-content-between align-items-start gap-2">
                            <div className="fw-bold">{s.name}</div>
                            <Button size="sm" variant="link" className="p-0 flex-shrink-0"
                              style={{ fontSize: ".72rem", color: "#000", textDecoration: "underline" }}
                              onClick={() => setExpanded(open ? "" : s.id)}>
                              {open ? "Hide details ▴" : "Details ▾"}
                            </Button>
                          </div>
                          <div style={{ color: "#6d6d6d", fontSize: ".78rem" }}>{s.description}</div>
                          {open && (
                            <div className="mt-2 p-2" style={{ background: "#f6f6f4", borderRadius: 6, borderLeft: "4px solid #000" }}>
                              <div style={{ fontSize: ".68rem", letterSpacing: ".1em", textTransform: "uppercase", fontWeight: 700, marginBottom: 4 }}>
                                What you get after selecting this scheme
                              </div>
                              <ul className="mb-1" style={{ fontSize: ".78rem", paddingLeft: "1.1rem" }}>
                                {String(s.benefits).split("•").map((b: string, i: number) =>
                                  b.trim() ? <li key={i}>{b.trim()}</li> : null)}
                              </ul>
                              <div style={{ fontSize: ".72rem", color: "#6d6d6d" }}>
                                Selecting a scheme embeds it in your application form and the officer's
                                review — the sanctioned outcome references every selected scheme.
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </ListGroup.Item>
                  );
                })}
              </ListGroup>
            </div>
          ))}
          <div className="d-flex justify-content-between align-items-center mt-2" style={{ fontSize: ".8rem", color: "#6d6d6d" }}>
            <span>{selected.size} scheme(s) selected</span>
            <span className="mono" style={{ fontSize: ".66rem" }}>
              {pickedAppId ? `attached to application ${pickedAppId.slice(-8)}` : "saved locally — attaches on application creation"}
            </span>
          </div>
        </Card.Body></Card>
      </Col>
      <Col lg={4}>
        <Card className="stat-card"><Card.Body>
          <h5 className="fw-bold mb-2">Not yet eligible</h5>
          {data.others.slice(0, 6).map((s: any) => (
            <div key={s.id} className="py-2" style={{ borderBottom: "1px solid #ecece8", fontSize: ".78rem" }}>
              <div className="fw-bold">{s.name}</div>
              <div className="mono" style={{ fontSize: ".64rem", color: "#6d6d6d" }}>{s.category || ""}</div>
              <div style={{ color: "#6d6d6d", fontSize: ".72rem" }}>{s.explanation}</div>
            </div>
          ))}
          <div className="principle-bar mt-3"><strong>Rule-based only</strong> — advisory, not a scheme guarantee.</div>
        </Card.Body></Card>
      </Col>
    </Row>
  );
}

function ApplicationsTab({ apps, checklist, reload, setMsg, setErr, onPickApp }: {
  apps: AppRow[]; checklist: Checklist | null;
  reload: () => void; setMsg: (s: string) => void; setErr: (s: string) => void;
  onPickApp: (id: string) => void;
}) {
  const [appId, setAppId] = useState("");
  const [busyId, setBusyId] = useState("");
  const [appDetail, setAppDetail] = useState<any>(null);

  async function apply(checklistApprovalId: string) {
    setErr(""); setMsg("");
    try {
      const r = await createApplication(checklistApprovalId);
      // Auto-attach schemes the applicant selected before creating the application.
      const saved: string[] = JSON.parse(localStorage.getItem("indus_scheme_pick") || "[]");
      if (r?.application_id && saved.length) {
        try {
          await updateSelectedSchemes(r.application_id, saved);
          localStorage.removeItem("indus_scheme_pick");
          setMsg("Application created — your selected schemes were attached automatically.");
        } catch { setMsg("Application created. Re-select schemes in the Schemes tab."); }
      } else {
        setMsg("Application created.");
      }
      reload();
    }
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
      setMsg(`Unified Application Form generated (verify code ${meta.verification_code}${meta.kyc_bound ? ", e-KYC bound" : ""}). Click Form PDF to download.`);
      reload();
    } catch (e: any) { setErr(e.message); }
    finally { setBusyId(""); }
  }

  async function autoFillForm(id: string) {
    setBusyId(id); setErr(""); setMsg("");
    try {
      const r = await autoFillFromData(id);
      const s = r.sources;
      setMsg(`Form auto-filled from ${s.profile_filled ? "profile · " : ""}${s.kyc_bound ? "e-KYC · " : ""}${s.schemes_selected} scheme(s) · ${s.documents_uploaded} doc(s). Your application form is ready below — download the Form PDF, review it, then click Confirm & Submit.`);
      reload();
    } catch (e: any) { setErr(e.message); }
    finally { setBusyId(""); }
  }

  async function confirmSubmit(id: string) {
    setBusyId(id); setErr(""); setMsg("");
    try {
      const r = await submitWithForm(id);
      setMsg(`Form ${r.form_verification_code} confirmed & submitted — instantly dispatched to the officer portal.`);
      reload();
    } catch (e: any) { setErr(e.message); }
    finally { setBusyId(""); }
  }

  async function resubmit(id: string) {
    setBusyId(id); setErr(""); setMsg("");
    try {
      await resubmitApplication(id);
      setMsg("Re-submitted after corrections — back to officer queue.");
      reload();
    } catch (e: any) { setErr(e.message); }
    finally { setBusyId(""); }
  }

  async function dlForm(id: string) {
    setErr(""); setMsg("");
    try { await downloadFormPdf(id); setMsg("Form PDF downloaded."); }
    catch (e: any) { setErr(e.message); }
  }

  async function dlCert(id: string) {
    setErr(""); setMsg("");
    try { await downloadCertificatePdf(id); setMsg("Sanctioned letter downloaded."); }
    catch (e: any) { setErr(e.message); }
  }

  async function openDetail(id: string) {
    setErr(""); setMsg("");
    try {
      const { api, getToken } = await import("@/lib/api");
      const token = getToken();
      const res = await fetch("/api/applications/" + id, {
        headers: token ? { Authorization: "Bearer " + token } : {},
      });
      const data = await res.json();
      setAppDetail(data);
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <Row className="g-3">
      <Col lg={8}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Step 5 · Your Applications</span>
          <h4 className="fw-bolder mb-3 mt-1">AI auto-fills the form — you only review & submit.</h4>
          {apps.length === 0 ? (
            <div className="text-center py-4" style={{ color: "#6d6d6d" }}><FileCheck2 size={28} strokeWidth={1.2} className="mb-2" /><p style={{ fontSize: ".82rem" }}>No applications yet.</p></div>
          ) : (
            <div className="table-responsive">
              <table className="table table-borderless align-middle">
                <thead><tr style={{ borderBottom: "1.5px solid #000" }}>
                  <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>ID</th>
                  <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>Approval</th>
                  <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>Status</th>
                  <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>Docs</th>
                  <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>Readiness</th>
                  <th style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase" }}>Real-time SLA</th>
                  <th></th>
                </tr></thead>
                <tbody>
                  {apps.map(a => (
                    <Row1 key={a.id} a={a} busyId={busyId}
                      onSubmit={() => submit(a.id)}
                      onGenForm={() => genForm(a.id)}
                      onFillForm={() => autoFillForm(a.id)}
                      onConfirmSubmit={() => confirmSubmit(a.id)}
                      onResubmit={() => resubmit(a.id)}
                      onDlForm={() => dlForm(a.id)}
                      onDlCert={() => dlCert(a.id)}
                      onDetail={() => openDetail(a.id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card.Body></Card>
        {appDetail && (
          <Card className="stat-card mt-3"><Card.Body>
            <div className="d-flex justify-content-between align-items-center mb-2">
              <span className="kicker">Application detail</span>
              <Button size="sm" className="btn-mono btn-outline-mono" onClick={() => setAppDetail(null)}>Close</Button>
            </div>
            <ApplicationDetail detail={appDetail} />
          </Card.Body></Card>
        )}
      </Col>
      <Col lg={4}>
        <Card className="stat-card"><Card.Body>
          <span className="kicker">Quick create</span>
          <h5 className="fw-bold mb-2 mt-1">New application</h5>
          <Form.Group className="mb-3">
            <Form.Label style={{ fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", fontWeight: 700 }}>Approval</Form.Label>
            {(checklist?.approvals || []).length > 0 ? (
              <Form.Select value={appId} onChange={e => setAppId(e.target.value)} style={{ fontSize: ".82rem" }}>
                <option value="">Pick your sector's approval…</option>
                {(checklist.approvals as any[]).map(a => (
                  <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                ))}
              </Form.Select>
            ) : (
              <Form.Control value={appId} onChange={e => setAppId(e.target.value)} placeholder="Save your profile first to see approvals" className="mono" style={{ fontSize: ".82rem" }} disabled />
            )}
            <div className="mt-1" style={{ fontSize: ".7rem", color: "#6d6d6d" }}>
              Choose an approval from your personalised checklist — this box only accepts your sector's approvals.
            </div>
          </Form.Group>
          <Button className="btn-mono w-100" disabled={!appId} onClick={() => apply(appId)}><PlusCircle size={14} strokeWidth={2} /> Create</Button>
          <div className="principle-bar mt-3"><strong>Tip:</strong> After creation, the AI auto-fill button will populate the form from your DigiLocker data + selected schemes + uploaded documents.</div>
        </Card.Body></Card>
      </Col>
    </Row>
  );
}

function Row1({ a, busyId, onSubmit, onGenForm, onFillForm, onConfirmSubmit, onResubmit, onDlForm, onDlCert, onDetail }: any) {
  const remaining = a.sla?.remaining_hours;
  const slaColor = a.sla?.state === "breached" ? "#ff3b30" : a.sla?.state === "at_risk" ? "#ff9f0a" : "#000";
  return (
    <tr style={{ borderBottom: "1px solid #ecece8" }}>
      <td className="mono" style={{ fontSize: ".74rem" }}>{a.id.slice(-8)}</td>
      <td><span className="fw-bold">{a.approval_code}</span><div style={{ color: "#6d6d6d", fontSize: ".72rem" }}>{a.department}</div></td>
      <td><Badge style={{ background: "transparent", color: "#000", border: "1.5px solid #000", borderRadius: 3, fontSize: ".62rem", fontWeight: 700, letterSpacing: ".08em" }}>{a.status.replace(/_/g, " ").toUpperCase()}</Badge></td>
      <td>
        {a.docs_pending ? (
          <Badge style={{ background: "transparent", color: "#ff9f0a", border: "1.5px solid #ff9f0a", borderRadius: 3, fontSize: ".62rem", fontWeight: 700, letterSpacing: ".06em" }}>
            VERIFY PENDING
          </Badge>
        ) : a.docs_count ? (
          <span className="text-success mono" style={{ fontSize: ".72rem", fontWeight: 700 }}>✓ {a.docs_passed}/{a.docs_total}</span>
        ) : (
          <span className="mono" style={{ fontSize: ".72rem", color: "#6d6d6d" }}>—</span>
        )}
      </td>
      <td>
        <div className="d-flex align-items-center gap-2">
          <ProgressBar now={a.readiness_score || 0} style={{ flex: 1, height: 4, borderRadius: 0, background: "#e7e7e2" }} />
          <span className="mono" style={{ fontSize: ".72rem" }}>{a.readiness_score || 0}%</span>
        </div>
      </td>
      <td>
        <div className="d-flex flex-column" style={{ fontSize: ".72rem" }}>
          <span className="mono fw-bold" style={{ color: slaColor }}>
            {remaining !== null && remaining !== undefined
              ? (remaining < 0
                  ? `Overdue ${Math.abs(Math.round(remaining))}h`
                  : `${Math.round(remaining)}h left`)
              : "—"}
          </span>
          <span style={{ color: "#6d6d6d" }}>
            {a.sla?.deadline ? new Date(a.sla.deadline).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) : "—"}
          </span>
        </div>
      </td>
      <td className="text-end">
        <div className="d-inline-flex gap-1 flex-wrap justify-content-end">
          {(a.status === "draft" || a.status === "returned") && (
            <>
              <Button size="sm" className="btn-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }}
                disabled={busyId === a.id} onClick={onFillForm}
                title="AI auto-fills the form from DigiLocker KYC + selected schemes + uploaded documents — you review it first">
                <Zap size={12} /> {busyId === a.id ? "…" : "Fill Form (AI)"}
              </Button>
              <Button size="sm" className="btn-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem", background: "#0a0", borderColor: "#0a0", color: "#fff" }}
                disabled={busyId === a.id} onClick={onConfirmSubmit}
                title="Confirm the auto-filled form and dispatch it to the officer portal">
                <Send size={12} /> Confirm & Submit
              </Button>
              <Button size="sm" className="btn-mono btn-outline-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }}
                disabled={busyId === a.id} onClick={onGenForm}>
                <FileText size={12} /> Generate PDF
              </Button>
              <Link href={`/applicant/upload?app=${a.id}`}><Button size="sm" className="btn-mono btn-outline-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }}>Docs</Button></Link>
            </>
          )}
          {a.status === "returned" && (
            <Button size="sm" className="btn-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem", background: "#ff9f0a", borderColor: "#ff9f0a" }}
              disabled={busyId === a.id} onClick={onResubmit}>
              <RefreshCw size={12} /> Resubmit
            </Button>
          )}
          {a.status !== "draft" && a.status !== "returned" && (
            <Button size="sm" className="btn-mono btn-outline-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }} onClick={onDlForm}>
              <FileDown size={12} /> Form PDF
            </Button>
          )}
          {a.status === "approved" && a.certificate && (
            <Button size="sm" className="btn-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem", background: "#0a0", borderColor: "#0a0", color: "#fff" }}
              onClick={onDlCert}
              title="Sanctioned letter generated by the officer after final approval">
              <Shield size={12} /> Sanction Letter (PDF)
            </Button>
          )}
          <Button size="sm" className="btn-mono btn-outline-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }} onClick={onDetail}>
            <ArrowRight size={12} /> Detail
          </Button>
        </div>
      </td>
    </tr>
  );
}

function ApplicationDetail({ detail }: { detail: any }) {
  const app = detail?.application;
  const cls = detail?.application?.clarifications || [];
  const ins = detail?.inspections || [];
  const sc = detail?.application?.schemes_selected || [];
  return (
    <div>
      <div className="row g-2">
        <div className="col-6"><span className="kicker">Approval</span><div className="fw-bold">{app?.approval_code} · {app?.approval_name}</div></div>
        <div className="col-6"><span className="kicker">Department</span><div>{app?.department}</div></div>
        <div className="col-6"><span className="kicker">Status</span><div>{app?.status?.replace(/_/g, " ").toUpperCase()}</div></div>
        <div className="col-6"><span className="kicker">SLA Deadline</span><div>{app?.sla_deadline?.slice(0, 16) || "—"}</div></div>
        <div className="col-6"><span className="kicker">Decision source</span><div>{app?.decision_source || "—"}</div></div>
        <div className="col-6"><span className="kicker">Readiness</span><div>{app?.readiness_score || 0}%</div></div>
      </div>
      {app?.feedback && (
        <Alert variant="warning" className="mt-3 mb-2" style={{ fontSize: ".82rem" }}>
          <div className="d-flex align-items-start gap-2">
            <AlertTriangle size={14} className="mt-1" />
            <div>
              <strong>Officer sent this back:</strong>
              <div style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>{app.feedback}</div>
              <em style={{ fontSize: ".74rem" }}>Re-fill the application per the corrections above and click Resubmit.</em>
            </div>
          </div>
        </Alert>
      )}
      {cls.length > 0 && (
        <div className="mt-3">
          <span className="kicker">Clarifications</span>
          {cls.map((c: any) => (
            <div key={c.id} className="p-2 mt-2" style={{ background: "#f6f6f4", borderLeft: "3px solid #000", borderRadius: 4 }}>
              <div style={{ fontSize: ".78rem" }}><strong>{c.status.toUpperCase()}</strong> · {c.created_at?.slice(0, 16)}</div>
              <div style={{ fontSize: ".82rem", whiteSpace: "pre-wrap" }}>{c.final_text}</div>
              {c.applicant_response && (
                <div className="mt-2" style={{ fontSize: ".78rem", color: "#000" }}>
                  <strong>Your response:</strong> {c.applicant_response}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {sc.length > 0 && (
        <div className="mt-3">
          <span className="kicker">Selected schemes ({sc.length})</span>
          <div className="d-flex flex-wrap gap-2 mt-1">
            {sc.map((s: any) => (
              <span key={s.scheme_id} className="badge border text-dark" style={{ background: "#f6f6f4" }}>{s.scheme_id}</span>
            ))}
          </div>
        </div>
      )}
      {ins.length > 0 && (
        <div className="mt-3">
          <span className="kicker">Inspections</span>
          {ins.map((i: any) => (
            <div key={i.id} style={{ fontSize: ".78rem", borderBottom: "1px solid #ecece8", padding: "4px 0" }}>
              {i.type} · {i.scheduled_date || "TBD"} · {i.status}
            </div>
          ))}
        </div>
      )}
    </div>
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
