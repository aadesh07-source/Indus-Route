// @ts-nocheck
"use client";
import { useState } from "react";
import { Offcanvas, Card, Button, Form, ListGroup } from "react-bootstrap";
import { CheckCircle2, XCircle, Send, Calendar, Eye, UserCheck, Shield, Zap, FileDown, FileCheck2 } from "lucide-react";
import { assignApplication, getPreScrutiny, officerDecision, scheduleInspection, getToken, downloadFormPdf } from "@/lib/api";

export default function OfficerReviewPanel({ selected, onClose, onReload, onMsg, onErr }: any) {
  const [prescrutiny, setPrescrutiny] = useState<any>(null);
  const [draft, setDraft] = useState<any>(null);
  const [clarText, setClarText] = useState("");
  const [inspDate, setInspDate] = useState("");

  async function open() {
    if (!selected) return;
    onErr(""); onMsg(""); setDraft(null); setClarText("");
    try { setPrescrutiny(await getPreScrutiny(selected.id)); }
    catch (e: any) { onErr(e.message); }
  }

  async function act(action: string, extra: object = {}) {
    if (!selected) return;
    onErr(""); onMsg("");
    try {
      const res = await officerDecision(selected.id, action, "", (extra as any).clarification_text);
      onMsg(`Decision '${action}' recorded (${res.status}).`);
      onReload(); onClose();
    } catch (e: any) { onErr(e.message); }
  }

  async function assign() {
    if (!selected) return;
    try { await assignApplication(selected.id); onMsg("Assigned to you."); onReload(); }
    catch (e: any) { onErr(e.message); }
  }

  async function getDraft() {
    if (!selected) return;
    try {
      const token = getToken();
      const res = await fetch(`/api/officer/applications/${selected.id}/draft-clarification`,
        { method: "POST", headers: token ? { Authorization: "Bearer " + token } : {} });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Draft failed");
      setDraft(data); setClarText(data.draft || "");
    } catch (e: any) { onErr(e.message); }
  }

  async function schedule() {
    if (!selected || !inspDate) return;
    try { await scheduleInspection(selected.id, inspDate, []); onMsg("Inspection scheduled for " + inspDate); }
    catch (e: any) { onErr(e.message); }
  }

  if (!selected) return null;

  return (
    <Offcanvas show={!!selected} onHide={onClose} onShow={open} placement="end" className="offcanvas-dark" style={{ width: "600px", maxWidth: "90vw" }}>
      <Offcanvas.Header closeButton><Offcanvas.Title>
        <span className="kicker">Review</span><h4 className="fw-bolder mb-0 mt-1">{selected.business_name}</h4>
        <span className="mono" style={{ fontSize: ".74rem", color: "#c9c9c4" }}>{selected.approval_code} · {selected.id.slice(-8)}</span>
      </Offcanvas.Title></Offcanvas.Header>
      <Offcanvas.Body>
        {!selected.assigned_officer_id && <Button className="btn-mono mb-3" onClick={assign}><UserCheck size={14} /> Assign to me</Button>}
        {prescrutiny?.form && (
          <Card className="ai-summary-card mb-3"><Card.Body>
            <span className="kicker" style={{ color: "#8f8f8f" }}>Auto-Generated Form</span>
            <div className="d-flex justify-content-between align-items-center mt-1">
              <div style={{ fontSize: ".78rem", color: "#c9c9c4" }}>
                <strong>{prescrutiny.form.verification_code}</strong> · {prescrutiny.form.source}
                {prescrutiny.form.submitted_at ? " · submitted" : ""}
              </div>
              <Button size="sm" className="btn-mono btn-outline-mono" onClick={() => downloadFormPdf(selected.id).catch((e: any) => onErr(e.message))}>
                <FileDown size={12} /> View PDF
              </Button>
            </div>
            <div className="principle-bar mt-2"><strong>Machine-filled</strong> — e-KYC data + rule engine; hash-tamper-evident.</div>
          </Card.Body></Card>
        )}
        {prescrutiny && (<>
          <Card className="ai-summary-card mb-3"><Card.Body>
            <span className="kicker" style={{ color: "#8f8f8f" }}>AI Pre-Scrutiny</span>
            <p style={{ fontSize: ".82rem", color: "#c9c9c4" }}>{prescrutiny.ai_summary?.text}</p>
            <div className="principle-bar mt-2"><strong>Not a verdict</strong> — officer decides.</div>
          </Card.Body></Card>
          <Card style={{ background: "#111", borderColor: "#333" }} className="mb-3"><Card.Body>
            <h5 className="fw-bold mb-2">Document checks</h5>
            {prescrutiny.deterministic_data?.documents?.map((d: any) => (
              <div key={d.id} className="d-flex justify-content-between py-1" style={{ borderBottom: "1px solid #333", fontSize: ".78rem" }}>
                <span>{d.label || d.type}</span>
                <span className={`mono fw-bold ${d.checks_passed === d.checks_total ? "text-success" : "text-danger"}`}>{d.checks_passed}/{d.checks_total}</span>
              </div>
            ))}
          </Card.Body></Card>
        </>)}
        {prescrutiny?.one_click && (
          <Card style={{ background: "#111", borderColor: prescrutiny.one_click.all_green ? "#0a0" : "#333" }} className="mb-3"><Card.Body>
            <div className="d-flex justify-content-between align-items-center">
              <h5 className="fw-bold mb-0">Statutory checklist</h5>
              {prescrutiny.one_click.all_green
                ? <span className="text-success fw-bold" style={{ fontSize: ".8rem" }}>ALL PARAMETERS GREEN</span>
                : <span style={{ color: "#ff9f0a", fontSize: ".8rem" }}>PENDING ITEMS</span>}
            </div>
            {prescrutiny.one_click.required_matrix?.map((m: any) => (
              <div key={m.doc_type} className="d-flex justify-content-between py-1" style={{ borderBottom: "1px solid #333", fontSize: ".78rem" }}>
                <span>{m.doc_type.replace(/_/g, " ")}</span>
                {m.state === "green" ? <span className="text-success mono">✓ {m.checks_passed}/{m.checks_total}</span>
                  : m.state === "failing" ? <span className="text-danger mono">✗ {m.checks_passed}/{m.checks_total}</span>
                  : <span style={{ color: "#ff9f0a" }}>not uploaded</span>}
              </div>
            ))}
            <div className="principle-bar mt-2"><strong>Rules decided readiness ({prescrutiny.one_click.readiness_100 ? "100/100" : "incomplete"})</strong> — approval remains the officer's call.</div>
            {prescrutiny.one_click.all_green && (
              <Button className="btn-mono w-100 mt-2" style={{ background: "#0a0", borderColor: "#0a0", color: "#000" }} onClick={() => act("approve")}>
                <Zap size={14} /> 1-Click Instant Approve
              </Button>
            )}
          </Card.Body></Card>
        )}
        <div className="d-flex flex-wrap gap-2 mt-3 mb-4">
          <Button className="btn-mono" onClick={() => act("verify")}><CheckCircle2 size={14} /> Verify</Button>
          <Button className="btn-mono" onClick={() => act("approve")}><Shield size={14} /> Approve</Button>
          <Button className="btn-mono btn-outline-mono" style={{ borderColor: "#ff3b30", color: "#ff3b30" }} onClick={() => act("reject")}><XCircle size={14} /> Reject</Button>
          <Button className="btn-mono btn-outline-mono" onClick={getDraft}><Eye size={14} /> Draft clarification</Button>
        </div>
        {draft && (<div className="mb-3">
          <p style={{ fontSize: ".72rem", color: "#c9c9c4" }} className="mb-1">AI draft ({draft.source}) — edit before sending.</p>
          <Form.Control as="textarea" rows={4} value={clarText} onChange={(e: any) => setClarText(e.target.value)} style={{ fontSize: ".82rem", background: "#0a0a0a", color: "#fff", borderColor: "#333" }} />
          <Button className="btn-mono mt-2" onClick={() => act("clarify", { clarification_text: clarText })}><Send size={14} /> Send clarification</Button>
        </div>)}
        <div className="d-flex gap-2 mt-3">
          <Form.Control type="date" value={inspDate} onChange={(e: any) => setInspDate(e.target.value)} style={{ fontSize: ".82rem", background: "#0a0a0a", color: "#fff", borderColor: "#333" }} />
          <Button className="btn-mono flex-shrink-0" onClick={schedule}><Calendar size={14} /> Schedule inspection</Button>
        </div>
      </Offcanvas.Body>
    </Offcanvas>
  );
}
