// @ts-nocheck
"use client";
import { useEffect, useState } from "react";
import { Card, ListGroup, Badge, Button, Modal, Form, Alert } from "react-bootstrap";
import Link from "next/link";
import { Upload, ScanLine, FileCheck2, Lock, RefreshCw, FolderUp } from "lucide-react";
import { listApplications, getFetchableDocs, fetchDigiLockerDocs } from "@/lib/api";

export default function DocumentsTab() {
  const [apps, setApps] = useState<any[]>([]);
  const [show, setShow] = useState(false);
  const [activeApp, setActiveApp] = useState<any>(null);
  const [picker, setPicker] = useState<any>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [digiMsg, setDigiMsg] = useState("");
  const [digiErr, setDigiErr] = useState("");

  useEffect(() => {
    listApplications()
      .then((r) => setApps(r.applications || []))
      .catch(() => {});
  }, []);

  async function openPicker(a: any) {
    setDigiMsg(""); setDigiErr(""); setPicked([]);
    setActiveApp(a); setShow(true); setPicker(null);
    try {
      const r = await getFetchableDocs(a.id);
      setPicker(r);
    } catch (e: any) { setDigiErr(e.message); }
  }

  async function doFetch() {
    if (!activeApp || picked.length === 0) return;
    setBusy(true); setDigiMsg(""); setDigiErr("");
    try {
      const r = await fetchDigiLockerDocs({ application_id: activeApp.id, doc_types: picked });
      const lines = (r.fetched || []).map((f) =>
        `✓ ${f.label} — ${f.issuer} — ${f.summary.checks_passed}/${f.summary.checks_total} checks passed`);
      setDigiMsg(lines.length
        ? `Fetched ${lines.length} Issued Document(s) from DigiLocker (mode: ${r.mode}):\n${lines.join("\n")}`
          + (r.still_pending?.length ? `\nStill pending (manual upload): ${r.still_pending.join(", ")}` : "")
        : "No new documents fetched.");
      setPicked([]);
      const fresh = await getFetchableDocs(activeApp.id);
      setPicker(fresh);
      listApplications().then((x) => setApps(x.applications || [])).catch(() => {});
    } catch (e: any) { setDigiErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <Card className="stat-card">
      <Card.Body>
        <div className="d-flex justify-content-between align-items-start flex-wrap gap-2">
          <div>
            <span className="kicker">Documents</span>
            <h4 className="fw-bolder mb-1 mt-1">Fetch from DigiLocker or Upload</h4>
            <p style={{ color: "#6d6d6d", fontSize: ".82rem", maxWidth: 560 }}>
              Issued Documents (PAN, GST certificate, signed declarations) can be fetched
              straight from your DigiLocker — digitally signed by the issuing authority and
              re-validated by the deterministic checks on arrival. Physical artefacts
              (layout plans, lease deeds) are uploaded manually.
            </p>
          </div>
          <Link href="/applicant/upload" className="btn btn-mono">
            <Upload size={14} strokeWidth={2} /> Quick Upload (Manual)
          </Link>
        </div>
        <ListGroup variant="flush" className="mt-3">
          {apps.length === 0 && (
            <ListGroup.Item className="px-0 text-center py-4" style={{ color: "#6d6d6d" }}>
              No applications yet — create one from the checklist first.
            </ListGroup.Item>
          )}
          {apps.map((a) => {
            const pending = a.docs_pending;
            return (
              <ListGroup.Item key={a.id} className="px-0 py-3" style={{ borderBottom: "1px solid #ecece8" }}>
                <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
                  <div>
                    <span className="fw-bold">{a.approval_code}</span>
                    <span style={{ color: "#6d6d6d", fontSize: ".76rem" }}> · {a.department}</span>
                    <div className="mono" style={{ fontSize: ".7rem", color: "#9a9a94" }}>{a.id.slice(-8)}</div>
                  </div>
                  <div className="d-flex align-items-center gap-2">
                    {pending ? (
                      <Badge style={{ background: "transparent", color: "#ff9f0a", border: "1.5px solid #ff9f0a", fontSize: ".64rem", fontWeight: 700, letterSpacing: ".06em" }}>
                        <ScanLine size={11} className="me-1" />VERIFY PENDING
                      </Badge>
                    ) : a.docs_count ? (
                      <Badge style={{ background: "#000", color: "#fff", fontSize: ".64rem", fontWeight: 700, letterSpacing: ".06em" }}>
                        <FileCheck2 size={11} className="me-1" />VERIFIED ✓ {a.docs_passed}/{a.docs_total}
                      </Badge>
                    ) : (
                      <Badge style={{ background: "transparent", color: "#6d6d6d", border: "1.5px solid #ccc", fontSize: ".64rem", fontWeight: 700, letterSpacing: ".06em" }}>NO DOCS</Badge>
                    )}
                    <Button size="sm" className="btn-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }}
                      onClick={() => openPicker(a)} title="Select required documents and fetch them from your DigiLocker (consent-based)">
                      <Lock size={12} /> Fetch from DigiLocker
                    </Button>
                    <Link href={`/applicant/upload?app=${a.id}`} className="btn btn-mono btn-outline-mono" style={{ padding: ".3rem .7rem", fontSize: ".68rem" }}>
                      <FolderUp size={12} /> Manual upload
                    </Link>
                  </div>
                </div>
              </ListGroup.Item>
            );
          })}
        </ListGroup>
      </Card.Body>

      <Modal show={show} onHide={() => setShow(false)} centered size="lg">
        <Modal.Header closeButton style={{ borderBottom: "2px solid #000" }}>
          <div>
            <span className="kicker">DigiLocker · Consent-based Issued Document fetch</span>
            <h5 className="fw-bolder mb-0 mt-1">
              Select documents {activeApp ? `— ${activeApp.approval_code}` : ""}
            </h5>
          </div>
        </Modal.Header>
        <Modal.Body>
          {digiErr && <Alert variant="danger" style={{ fontSize: ".8rem" }}>{digiErr}</Alert>}
          {digiMsg && <Alert variant="success" style={{ fontSize: ".8rem", whiteSpace: "pre-line" }}>{digiMsg}</Alert>}
          {!picker && !digiErr && (
            <div className="text-center py-4" style={{ color: "#6d6d6d" }}>
              <RefreshCw size={20} className="me-2" /> Loading your DigiLocker document options…
            </div>
          )}
          {picker && (
            <>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span style={{ fontSize: ".72rem", color: "#6d6d6d" }}>
                  Issued Documents are digitally signed by the issuing authority — never re-uploaded, only consented.
                </span>
                <Badge style={{ background: picker.mode === "sandbox" ? "#f4f4f0" : "#000", color: picker.mode === "sandbox" ? "#555" : "#fff", border: "1px solid #ccc", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".08em" }}>
                  {picker.mode === "sandbox" ? "SANDBOX MODE" : "PRODUCTION"}
                </Badge>
              </div>
              <DigiDocList picker={picker} picked={picked} setPicked={setPicked} activeApp={activeApp} />
              <div className="principle-bar mt-3">
                <strong>How it works:</strong> on DigiLocker, you pick the documents and consent — we receive only what you allow,
                verify the issuer&apos;s digital signature, and run the same deterministic checks as manual uploads. Consent is revocable anytime.
              </div>
            </>
          )}
        </Modal.Body>
        <Modal.Footer style={{ borderTop: "1px solid #ecece8" }}>
          <Button size="sm" className="btn-mono btn-outline-mono" onClick={() => setShow(false)}>Close</Button>
          <Button size="sm" className="btn-mono" disabled={busy || picked.length === 0} onClick={doFetch}>
            <Lock size={13} /> {busy ? "Fetching…" : `Fetch ${picked.length} selected from DigiLocker`}
          </Button>
        </Modal.Footer>
      </Modal>
    </Card>
  );
}

function DigiDocList({ picker, picked, setPicked, activeApp }: any) {
  return (
    <ListGroup variant="flush" style={{ border: "1px solid #e5e5e0" }}>
      {picker.docs.map((d: any) => (
        <ListGroup.Item key={d.type} className="d-flex justify-content-between align-items-center py-3"
          style={{ borderBottom: "1px solid #efefe9" }}>
          <div className="d-flex align-items-start gap-2">
            {d.digilocker_issued ? (
              <Form.Check type="checkbox" className="mt-1"
                checked={picked.includes(d.type)}
                disabled={d.status === "uploaded"}
                onChange={(e) => setPicked((p: string[]) =>
                  e.target.checked ? [...p, d.type] : p.filter((t: string) => t !== d.type))} />
            ) : (
              <FolderUp size={16} className="mt-1" style={{ color: "#9a9a94" }} />
            )}
            <div>
              <div className="fw-bold" style={{ fontSize: ".84rem" }}>{d.label}</div>
              <div style={{ fontSize: ".72rem", color: "#6d6d6d" }}>
                {d.digilocker_issued
                  ? <>Issuer: {d.issuer} · <span className="mono">{d.consent_uri}</span></>
                  : <>Not a DigiLocker Issued Document — <Link href={`/applicant/upload?app=${activeApp?.id}`}>upload manually</Link></>}
              </div>
            </div>
          </div>
          {d.status === "uploaded" ? (
            <Badge style={{ background: "#000", color: "#fff", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".06em" }}>
              ✓ {d.checks_passed}/{d.checks_total}
            </Badge>
          ) : (
            <Badge style={{ background: "transparent", color: "#ff9f0a", border: "1.5px solid #ff9f0a", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".06em" }}>
              PENDING
            </Badge>
          )}
        </ListGroup.Item>
      ))}
    </ListGroup>
  );
}
