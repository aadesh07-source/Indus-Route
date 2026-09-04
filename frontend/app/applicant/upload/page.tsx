// @ts-nocheck
"use client";
import { useCallback, useEffect, useState } from "react";
import { Container, Row, Col, Card, Button, Form, Badge, ListGroup } from "react-bootstrap";
import Link from "next/link";
import { motion } from "motion/react";
import { ArrowLeft, Upload, ScanLine, FileCheck2, CheckCircle2, XCircle } from "lucide-react";
import { getToken, listApplications, uploadDocument, DOC_LABELS, titleCase } from "@/lib/api";

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

  const load = useCallback(async () => {
    try {
      const list = await listApplications();
      setApps(list.applications || []);
      setAuthed(true);
    } catch { setAuthed(false); }
  }, []);

  useEffect(() => { setAuthed(getToken() ? null : false); }, []);
  useEffect(() => { if (authed === null) load(); }, [authed, load]);
  useEffect(() => {
    const a = new URLSearchParams(window.location.search).get("app");
    if (a) setAppId(a);
  }, []);

  async function submit() {
    if (!appId || !file) return;
    setBusy(true); setErr(""); setMsg(""); setResult(null);
    try {
      const res = await uploadDocument(appId, docType, file, {});
      setResult(res);
      setMsg("Document scanned — " + res.summary.checks_passed + "/" + res.summary.checks_total + " checks passed.");
      load();
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
              <Form.Select value={appId} onChange={(e) => { setAppId(e.target.value); setResult(null); }}>
                <option value="">Select an application…</option>
                {apps.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.approval_code} · {a.department} ({a.status.replace(/_/g, " ")})
                  </option>
                ))}
              </Form.Select>
              {selected && (
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

            <Button className="btn-mono w-100 mt-3" disabled={!appId || !file || busy} onClick={submit}>
              {busy ? "Scanning with EasyOCR…" : <><ScanLine size={14} strokeWidth={2} /> Scan & Pre-Validate</>}
            </Button>
            <div className="principle-bar mt-3">
              <strong>How it works:</strong> EasyOCR reads the document, deterministic rules check every
              extracted field. The AI never decides pass/fail.
            </div>
          </Card.Body></Card>
        </Col>
        {/* ── Scan result / empty state ── */}
        <Col lg={7}>
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