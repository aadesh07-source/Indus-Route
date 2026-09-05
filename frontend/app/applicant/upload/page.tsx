// @ts-nocheck
"use client";
import { useCallback, useEffect, useState } from "react";
import { Container, Row, Col, Card, Button, Form, Badge, ListGroup, ProgressBar } from "react-bootstrap";
import Link from "next/link";
import { motion } from "motion/react";
import { ArrowLeft, Upload, ScanLine, FileCheck2, CheckCircle2, XCircle } from "lucide-react";
import { getToken, listApplications, uploadDocument, DOC_LABELS, titleCase, getMyProfile, getDocumentSpecs, getApplication } from "@/lib/api";

type AppRow = { id: string; status: string; approval_code: string; approval_name: string; department: string; documents?: any[] };

export default function UploadCentre() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [apps, setApps] = useState<AppRow[]>([]);
  const [appId, setAppId] = useState("");
  const [docType, setDocType] = useState("pan_card");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [specs, setSpecs] = useState<any[]>([]);
  const [profile, setProfile] = useState<any>(null);
  const [declared, setDeclared] = useState<Record<string, string>>({});
  const [detail, setDetail] = useState<any>(null);

  const load = useCallback(async () => {
    try {
      const list = await listApplications();
      setApps(list.applications || []);
      // Auto-select the first in-flight application so the readiness panel is live immediately.
      setAppId((prev) => {
        if (prev) return prev;
        const firstOpen = (list.applications || []).find(
          (x: any) => !["approved", "rejected", "provisionally_cleared"].includes(x.status));
        return firstOpen ? firstOpen.id : "";
      });
      setAuthed(true);
      try { setProfile((await getMyProfile()).profile); } catch { /* optional */ }
      setSpecs((await getDocumentSpecs()).specs || []);
    } catch { setAuthed(false); }
  }, []);

  // When the document type changes, reset the declared-data form with
  // sensible defaults pulled from the saved business profile (the applicant
  // must confirm each field — it is then verified by the deterministic rules).
  useEffect(() => {
    const spec = specs.find((s: any) => s.doc_type === docType);
    if (!spec) return;
    const init: Record<string, string> = {};
    for (const f of spec.extractable_fields || []) {
      if (f === "entity_name" || f === "legal_name") init[f] = profile?.name || "";
      if (f === "pan_number" && profile?.pan_masked) init[f] = "";
      if (f === "aadhaar_otp_verified") init[f] = "true";
    }
    setDeclared(init);
  }, [docType, specs, profile]);

  useEffect(() => { setAuthed(getToken() ? null : false); }, []);
  useEffect(() => { if (authed === null) load(); }, [authed, load]);
  // Live document readiness for the selected application (fetched with documents).
  const refreshDetail = useCallback(async () => {
    if (!appId) { setDetail(null); return; }
    try { setDetail(await getApplication(appId)); } catch { setDetail(null); }
  }, [appId]);
  useEffect(() => { refreshDetail(); }, [appId, refreshDetail]);
  useEffect(() => {
    const a = new URLSearchParams(window.location.search).get("app");
    if (a) setAppId(a);
  }, []);

  async function submit() {
    if (!appId || !file || selectedDecided) return;
    setBusy(true); setErr(""); setMsg(""); setResult(null);
    try {
      const res = await uploadDocument(appId, docType, file, declared);
      setResult(res);
      setMsg("Document scanned — " + res.summary.checks_passed + "/" + res.summary.checks_total + " checks passed.");
      await Promise.all([load(), refreshDetail()]);
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }
  if (authed === false) {
    return (
      <Container fluid="xxl" className="py-5">
        <Card className="mx-auto" style={{ maxWidth: 480 }}>
          <Card.Body className="p-4 text-center">
            <Upload size={32} strokeWidth={1.5} className="mb-3" />
            <h2 className="display-7 mb-2">Upload Centre</h2>
            <p style={{ color: "#6d6d6d" }}>Please <Link href="/login">sign in</Link> to upload documents.</p>
          </Card.Body>
        </Card>
      </Container>
    );
  }

  const selected = apps.find((a) => a.id === appId);
  // Applications with a final decision are locked — only in-flight ones accept documents.
  const DECIDED = ["approved", "rejected", "provisionally_cleared"];
  const editableApps = apps.filter((a) => !DECIDED.includes(a.status));
  const selectedDecided = !!selected && DECIDED.includes(selected.status);

  return (
    <Container fluid="xxl" className="py-4">
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-4">
        <div>
          <Link href="/applicant" className="kicker" style={{ textDecoration: "none" }}>
            <ArrowLeft size={13} strokeWidth={2.2} /> Back to portal
          </Link>
          <h1 className="display-6 mb-0 mt-1">Upload Centre</h1>
        </div>
      </div>

      {msg && <div className="alert alert-success py-2" style={{ borderLeft: "4px solid #000" }}>{msg}</div>}
      {err && <div className="alert alert-danger py-2" style={{ borderLeft: "4px solid #ff3b30" }}>{err}</div>}

      <Row className="g-3">
        {/* ── Upload form ── */}
        <Col lg={5}>
          <Card className="stat-card"><Card.Body>
            <span className="kicker">Step 1 · Target</span>
            <Form.Group className="mt-2 mb-3">
              <Form.Label className="stat-lbl">Application</Form.Label>
              {editableApps.length === 0 ? (
                <div className="alert alert-warning py-2 mb-0" style={{ fontSize: ".78rem", borderLeft: "4px solid #ff9f0a" }}>
                  All your applications already have a final decision, so they are locked for uploads.
                  Create a fresh draft application from the <Link href="/applicant">Application tab</Link> first —
                  documents are uploaded and pre-validated <strong>before</strong> you submit the form.
                </div>
              ) : (
                <Form.Select value={appId} onChange={(e) => { setAppId(e.target.value); setResult(null); }}>
                  <option value="">Select an application…</option>
                  {editableApps.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.approval_code} · {a.department} ({a.status.replace(/_/g, " ")})
                    </option>
                  ))}
                </Form.Select>
              )}
              {selectedDecided && (
                <div className="alert alert-warning py-2 mt-2 mb-0" style={{ fontSize: ".76rem", borderLeft: "4px solid #ff9f0a" }}>
                  This application already has a final decision — documents are locked.
                  Pick an in-flight application or <Link href="/applicant">create a new draft</Link>.
                </div>
              )}
              {selected && !selectedDecided && (
                <div className="mt-2" style={{ fontSize: ".76rem", color: "#6d6d6d" }}>
                  {selected.approval_name} · {selected.documents?.length || 0} document(s) uploaded so far
                </div>
              )}
            </Form.Group>

            <span className="kicker">Step 2 · Document type</span>
            <Form.Group className="mt-2 mb-3">
              <Form.Select value={docType} onChange={(e) => { setDocType(e.target.value); setResult(null); }}>
                {Object.entries(DOC_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Form.Select>
            </Form.Group>
            {/* Step 3 · file + scan */}
            <span className="kicker">Step 3 · File</span>
            <div
              className={"dz-drop mt-2" + (dragging ? " dz-dragging" : "")}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files?.[0]) { setFile(e.dataTransfer.files[0]); setResult(null); } }}
            >
              <div className="dz-icon"><ScanLine size={22} strokeWidth={1.5} /></div>
              {file ? (
                <div>
                  <div className="fw-bold" style={{ fontSize: ".84rem" }}>{file.name}</div>
                  <div className="mono" style={{ fontSize: ".7rem", color: "#6d6d6d" }}>{(file.size / 1024).toFixed(0)} KB · ready to scan</div>
                </div>
              ) : (
                <div>
                  <div className="fw-bold" style={{ fontSize: ".84rem" }}>Drag & drop the document here</div>
                  <div style={{ fontSize: ".74rem", color: "#6d6d6d" }}>PDF, PNG, JPG or TXT · max 10 MB</div>
                </div>
              )}
              <Form.Control type="file" accept=".pdf,.png,.jpg,.jpeg,.txt" className="mt-3"
                onChange={(e: any) => { setFile(e.target.files?.[0] || null); setResult(null); }} />
            </div>

            {specs.find((s: any) => s.doc_type === docType)?.extractable_fields?.length > 0 && (
              <>
                <span className="kicker mt-3">Step 3.5 · Confirm data on the document</span>
                <div className="mt-2 mb-1" style={{ fontSize: ".74rem", color: "#6d6d6d" }}>
                  Your scanned {DOC_LABELS[docType] || docType} will be checked against these declared values (same
                  deterministic rules as OCR). Confirm/edit them to match the scanned file.
                </div>
                {specs.find((s: any) => s.doc_type === docType).extractable_fields.map((f: string) => (
                  <Form.Group key={f} className="mb-2">
                    <Form.Label style={{ fontSize: ".66rem", letterSpacing: ".08em", textTransform: "uppercase", fontWeight: 700, marginBottom: 2 }}>
                      {titleCase(f.replace(/_/g, " "))}
                    </Form.Label>
                    <Form.Control
                      size="sm"
                      className="mono"
                      value={declared[f] || ""}
                      onChange={(e: any) => setDeclared((d: any) => ({ ...d, [f]: e.target.value }))}
                      placeholder={f === "pan_number" ? profile?.pan_masked || "Enter PAN" : "Enter value as printed"}
                      style={{ fontSize: ".8rem" }}
                    />
                  </Form.Group>
                ))}
              </>
            )}

            <Button className="btn-mono w-100 mt-3" disabled={!appId || !file || busy} onClick={submit}>
              {busy ? "Scanning & verifying…" : <><ScanLine size={14} strokeWidth={2} /> Scan & Pre-Validate</>}
            </Button>
            <div className="principle-bar mt-3">
              <strong>How it works:</strong> EasyOCR reads scanned images, deterministic rules check every
              extracted/declared field. The AI never decides pass/fail.
            </div>
          </Card.Body></Card>
        </Col>
        {/* ── Scan result / empty state ── */}
        <Col lg={7}>
          {selected && !selectedDecided && (
            <DocReadinessCard app={selected} docs={detail?.application?.documents || selected?.documents || []} />
          )}
          {result ? (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
              <Card className="stat-card mb-3"><Card.Body>
                <div className="d-flex justify-content-between align-items-start flex-wrap gap-2 mb-2">
                  <div>
                    <span className="kicker">Scan result</span>
                    <h4 className="fw-bolder mb-0 mt-1">{result.label}</h4>
                  </div>
                  <Badge className="mono" style={{ background: "#000", color: "#fff", fontSize: ".66rem", letterSpacing: ".1em", padding: "4px 10px" }}>
                    {result.ocr_source === "easyocr" ? "EASYOCR" : result.ocr_source === "text" ? "TEXT EXTRACT" : "DECLARED FIELDS"}
                  </Badge>
                </div>
                <div className="d-flex align-items-center gap-3 mb-3">
                  <div style={{ fontSize: "2rem", fontWeight: 850, letterSpacing: "-.04em" }}>
                    {result.summary.checks_passed}<span style={{ color: "#6d6d6d", fontSize: "1.1rem" }}>/{result.summary.checks_total}</span>
                  </div>
                  {result.summary.all_passed ? (
                    <Badge style={{ background: "#000", color: "#fff", fontSize: ".68rem", letterSpacing: ".1em" }}>PRE-VALIDATED ✓</Badge>
                  ) : (
                    <Badge style={{ background: "transparent", color: "#000", border: "1.5px solid #000", fontSize: ".68rem", letterSpacing: ".1em" }}>NEEDS ATTENTION</Badge>
                  )}
                </div>
                <h6 className="fw-bold mt-3 mb-2">Deterministic checks</h6>
                <CheckList checks={result.checks} />
              </Card.Body></Card>

              <Card className="stat-card"><Card.Body>
                <span className="kicker">Extracted fields</span>
                <h6 className="fw-bold mt-1 mb-3">Data read from your document</h6>
                <FieldTable fields={result.extracted_fields || {}} />
                <div className="chart-note mt-2">Extracted values are untrusted input — they only feed rule validators, never decisions.</div>
              </Card.Body></Card>
            </motion.div>
          ) : (
            <Card className="stat-card h-100"><Card.Body className="d-flex flex-column align-items-center justify-content-center text-center py-5">
              <FileCheck2 size={44} strokeWidth={1.1} className="mb-3" />
              <h5 className="fw-bolder">Scan results appear here</h5>
              <p style={{ color: "#6d6d6d", fontSize: ".82rem", maxWidth: 380 }}>
                Pick an application, choose a document type and upload the file. The scanner extracts
                fields with EasyOCR and runs every statutory check automatically — the same checks the
                officer will see during review.
              </p>
              <div className="table-modern-wrap w-100 mt-2" style={{ maxWidth: 420 }}>
                <table className="table-modern">
                  <thead><tr><th>Doc type</th><th>Validated automatically</th></tr></thead>
                  <tbody>
                    {Object.entries(DOC_LABELS).slice(0, 5).map(([k2, v]) => (
                      <tr key={k2}><td style={{ fontSize: ".78rem", fontWeight: 600 }}>{v}</td><td className="mono" style={{ fontSize: ".72rem" }}>rule-table ✓</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card.Body></Card>
          )}
        </Col>
      </Row>
    </Container>
  );
}

function DocReadinessCard({ app, docs }: { app: any; docs: any[] }) {
  const list = docs || [];
  const passed = list.reduce((s: number, d: any) => s + (d.checks_passed || 0), 0);
  const total = list.reduce((s: number, d: any) => s + (d.checks_total || 0), 0);
  const pct = total ? Math.round((100 * passed) / total) : 0;
  const allPre = list.length > 0 && list.every((d: any) => d.status === "pre_validated");
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Card className="stat-card mb-3"><Card.Body>
        <div className="d-flex justify-content-between align-items-start flex-wrap gap-2">
          <div>
            <span className="kicker">Document readiness · live</span>
            <h5 className="fw-bolder mb-0 mt-1">{app.approval_code} · {list.length} document(s) uploaded</h5>
          </div>
          <Badge className="mono" style={allPre
            ? { background: "#000", color: "#fff", fontSize: ".66rem", letterSpacing: ".1em", padding: "4px 10px" }
            : { background: "transparent", color: "#000", border: "1.5px solid #ff9f0a", fontSize: ".66rem", letterSpacing: ".1em", padding: "4px 10px" }}>
            {allPre ? "ALL PRE-VALIDATED ✓" : pct + "% CHECKS PASSED"}
          </Badge>
        </div>
        <ProgressBar now={pct} className="my-3" style={{ height: 8 }} />
        {list.length === 0 ? (
          <p style={{ color: "#6d6d6d", fontSize: ".8rem", marginBottom: 0 }}>
            No documents uploaded for this application yet. Every document you scan here is
            pre-validated instantly and its readiness shows up in this panel — the same results
            the officer sees during review.
          </p>
        ) : (
          <div className="table-modern-wrap" style={{ overflowX: "auto" }}>
            <table className="table-modern" style={{ minWidth: 420 }}>
              <thead><tr><th>Document</th><th className="text-end">Checks</th><th className="text-end">Status</th></tr></thead>
              <tbody>
                {list.map((d: any) => (
                  <tr key={d.id}>
                    <td>
                      <div className="fw-bold" style={{ fontSize: ".8rem" }}>{d.label || d.type}</div>
                      <span className="mono" style={{ fontSize: ".68rem", color: "#6d6d6d" }}>
                        {(d.filename || "").slice(0, 28)}{d.uploaded_at ? " · " + String(d.uploaded_at).slice(0, 16).replace("T", " ") : ""}
                      </span>
                    </td>
                    <td className="text-end mono fw-bold" style={{
                      fontSize: ".78rem",
                      color: d.checks_passed === d.checks_total ? "#0a0" : "#ff3b30",
                    }}>{d.checks_passed}/{d.checks_total}</td>
                    <td className="text-end">
                      <Badge style={d.status === "pre_validated"
                        ? { background: "#000", color: "#fff", fontSize: ".6rem", letterSpacing: ".08em" }
                        : { background: "transparent", color: "#000", border: "1.5px solid #ff9f0a", fontSize: ".6rem", letterSpacing: ".08em" }}>
                        {String(d.status || "pending").replace(/_/g, " ").toUpperCase()}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="chart-note mt-2">
          Pre-validated documents travel with the submitted form to the officer portal —
          the officer then verifies each document one by one before final clearance.
        </div>
      </Card.Body></Card>
    </motion.div>
  );
}

function CheckList({ checks }: { checks: any[] }) {
  return (
    <ListGroup variant="flush">
      {(checks || []).map((c: any, i: number) => (
        <ListGroup.Item key={i} className="px-0 py-2 d-flex align-items-start gap-2" style={{ borderBottom: "1px solid #ecece8" }}>
          {c.passed
            ? <CheckCircle2 size={15} strokeWidth={2.2} className="flex-shrink-0 mt-1" />
            : <XCircle size={15} strokeWidth={2.2} color="#ff3b30" className="flex-shrink-0 mt-1" />}
          <div>
            <div className="fw-bold" style={{ fontSize: ".8rem" }}>{c.description}</div>
            <div className="mono" style={{ fontSize: ".72rem", color: "#6d6d6d" }}>{c.reason}</div>
          </div>
        </ListGroup.Item>
      ))}
    </ListGroup>
  );
}

function FieldTable({ fields }: { fields: Record<string, any> }) {
  return (
    <div className="table-modern-wrap">
      <table className="table-modern">
        <thead><tr><th>Field</th><th>Value</th></tr></thead>
        <tbody>
          {Object.entries(fields).length === 0 && (
            <tr><td colSpan={2} style={{ padding: 14, color: "#6d6d6d", textAlign: "center" }}>No fields extracted — check the document legibility.</td></tr>
          )}
          {Object.entries(fields).map(([k2, v]) => (
            <tr key={k2}>
              <td className="mono" style={{ fontSize: ".72rem", width: "40%" }}>{titleCase(k2)}</td>
              <td style={{ fontSize: ".8rem", fontWeight: 600 }}>{String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}