// @ts-nocheck
"use client";
import { useState } from "react";
import { Offcanvas, Card, Button, Form, ListGroup } from "react-bootstrap";
import { CheckCircle2, XCircle, Send, Calendar, Eye, UserCheck, Shield, Zap, FileDown, FileCheck2, AlertTriangle, Award } from "lucide-react";
import { assignApplication, getPreScrutiny, officerDecision, scheduleInspection, getToken, downloadFormPdf, signParameter, draftSendback } from "@/lib/api";

export default function OfficerReviewPanel({ selected, onClose, onReload, onMsg, onErr }: any) {
  const [prescrutiny, setPrescrutiny] = useState<any>(null);
  const [draft, setDraft] = useState<any>(null);
  const [clarText, setClarText] = useState("");
  const [sendBackText, setSendBackText] = useState("");
  const [issueCert, setIssueCert] = useState(false);
  const [inspDate, setInspDate] = useState("");

  async function open() {
    if (!selected) return;
    onErr(""); onMsg(""); setDraft(null); setClarText(""); setSendBackText(""); setIssueCert(false);
    try { setPrescrutiny(await getPreScrutiny(selected.id)); }
    catch (e: any) { onErr(e.message); }
  }

  async function act(action: string, extra: object = {}) {
    if (!selected) return;
    onErr(""); onMsg("");
    try {
      const notes = (extra as any).notes ?? "";
      const res = await officerDecision(selected.id, action, notes, (extra as any).clarification_text);
      if (action === "approve" && res.sanction_letter) {
        onMsg(`Approved — sanction letter ${res.sanction_letter.certificate_no} generated and delivered to the applicant's portal.`);
      } else {
        onMsg(`Decision '${action}' recorded (${res.status}).`);
      }
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

  async function getSendbackDraft() {
    if (!selected) return;
    onErr(""); onMsg("");
    try {
      const r = await draftSendback(selected.id);
      setSendBackText(r.draft || "");
      onMsg("AI drafted the corrections list — review and edit before sending back.");
    } catch (e: any) { onErr(e.message); }
  }

  async function sendBack() {
    if (!selected || !sendBackText.trim()) return;
    onErr(""); onMsg("");
    try {
      await officerDecision(selected.id, "send_back", sendBackText.trim(), "");
      onMsg("Form sent back to applicant with your correction notes.");
      onReload(); onClose();
    } catch (e: any) { onErr(e.message); }
  }

  async function issueCertificate() {
    if (!selected) return;
    onErr(""); onMsg("");
    try {
      const token = getToken();
      const res = await fetch(`/api/officer/applications/${selected.id}/issue-certificate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({ certificate_type: "sanction_clearance" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Certificate issue failed");
      onMsg(`Certificate ${data.certificate_no} issued — applicant will see & download it in their portal.`);
      onReload(); onClose();
    } catch (e: any) { onErr(e.message); }
  }

  async function schedule() {
    if (!selected || !inspDate) return;
    try { await scheduleInspection(selected.id, inspDate, []); onMsg("Inspection scheduled for " + inspDate); }
    catch (e: any) { onErr(e.message); }
  }

  async function signParam(paramKey: string) {
    if (!selected) return;
    onErr(""); onMsg("");
    try {
      const res = await signParameter(selected.id, paramKey);
      onMsg(`Parameter approved — ${res.label}. ${res.remaining_parameters.length} parameter(s) remaining.`);
      setPrescrutiny(await getPreScrutiny(selected.id));
    } catch (e: any) { onErr(e.message); }
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
          <Card style={{ background: "#111", borderColor: prescrutiny.one_click.all_signed ? "#0a0" : "#333" }} className="mb-3"><Card.Body>
            <div className="d-flex justify-content-between align-items-center">
              <h5 className="fw-bold mb-0">Clearance parameters</h5>
              <span style={{ fontSize: ".78rem" }}>
                {prescrutiny.one_click.all_signed
                  ? <span className="text-success fw-bold">ALL APPROVED ✓</span>
                  : <span style={{ color: "#ff9f0a" }}>{prescrutiny.one_click.unsigned_count} pending</span>}
              </span>
            </div>
            <div className="mt-2 mb-3" style={{ background: "#0a0a0a", borderRadius: 4, padding: "6px 10px", fontSize: ".72rem", color: "#c9c9c4" }}>
              Review each clearance below — the AI/deterministic analysis is shown beside
              every parameter. Approve them one by one; Final Approve unlocks at the end.
            </div>
            {prescrutiny.parameters?.map((p: any) => (
              <div key={p.param_key} className="py-2" style={{ borderBottom: "1px solid #222", fontSize: ".78rem" }}>
                <div className="d-flex justify-content-between align-items-start gap-2">
                  <div>
                    <div className="fw-bold">{p.label}</div>
                    <div style={{ color: "#8f8f8f", fontSize: ".72rem", marginTop: 2 }}>{p.analysis}</div>
                  </div>
                  {p.signed ? (
                    <span className="text-success fw-bold flex-shrink-0" style={{ fontSize: ".72rem" }}>
                      {p.auto ? "NOT APPLICABLE" : "APPROVED ✓"}
                    </span>
                  ) : p.state === "green" ? (
                    <Button size="sm" className="btn-mono flex-shrink-0"
                      style={{ padding: ".2rem .6rem", fontSize: ".66rem" }}
                      onClick={() => signParam(p.param_key)}>
                      <CheckCircle2 size={11} /> Approve
                    </Button>
                  ) : (
                    <span style={{ color: p.state === "attention" ? "#ff9f0a" : "#ff3b30", fontSize: ".68rem" }} className="flex-shrink-0">
                      {p.state.toUpperCase()}
                    </span>
                  )}
                </div>
              </div>
            ))}
            <div className="principle-bar mt-2"><strong>Rules decided readiness ({prescrutiny.one_click.readiness_100 ? "100/100" : "incomplete"})</strong> — every green parameter needs your individual sign-off.</div>
            {prescrutiny.one_click.all_signed ? (
              <Button className="btn-mono w-100 mt-2" style={{ background: "#0a0", borderColor: "#0a0", color: "#000" }}
                onClick={() => act("approve")}>
                <Zap size={14} /> 1-Click Final Approve (all parameters verified)
              </Button>
            ) : (
              <Button className="btn-mono w-100 mt-2" disabled>
                <Shield size={14} /> Approve all parameters to unlock Final Approve
              </Button>
            )}
          </Card.Body></Card>
        )}
        <div className="d-flex flex-wrap gap-2 mt-3 mb-4">
          <Button className="btn-mono" onClick={() => act("verify")}><CheckCircle2 size={14} /> Verify</Button>
          <Button className="btn-mono" onClick={() => act("approve")}><Shield size={14} /> Approve</Button>
          <Button className="btn-mono btn-outline-mono" style={{ borderColor: "#ff3b30", color: "#ff3b30" }} onClick={() => act("reject")}><XCircle size={14} /> Reject</Button>
          <Button className="btn-mono btn-outline-mono" onClick={getDraft}><Eye size={14} /> Draft clarification</Button>
          <Button className="btn-mono btn-outline-mono" onClick={getSendbackDraft}><AlertTriangle size={14} /> Send back (AI draft)</Button>
        </div>
        {draft && (<div className="mb-3">
          <p style={{ fontSize: ".72rem", color: "#c9c9c4" }} className="mb-1">AI draft ({draft.source}) — edit before sending.</p>
          <Form.Control as="textarea" rows={4} value={clarText} onChange={(e: any) => setClarText(e.target.value)} style={{ fontSize: ".82rem", background: "#0a0a0a", color: "#fff", borderColor: "#333" }} />
          <Button className="btn-mono mt-2" onClick={() => act("clarify", { clarification_text: clarText })}><Send size={14} /> Send clarification</Button>
        </div>)}
        {sendBackText !== null && (
          <div className="mb-3">
            <p style={{ fontSize: ".72rem", color: "#ff9f0a" }} className="mb-1">
              <AlertTriangle size={11} className="me-1" />
              Send-back corrections — AI drafted, edit then send. Applicant will see this text on their portal.
            </p>
            <Form.Control as="textarea" rows={5} value={sendBackText} onChange={(e: any) => setSendBackText(e.target.value)}
              placeholder="Use 'AI draft' button to populate, then edit…"
              style={{ fontSize: ".82rem", background: "#0a0a0a", color: "#fff", borderColor: "#ff9f0a" }} />
            <Button className="btn-mono mt-2" style={{ background: "#ff9f0a", borderColor: "#ff9f0a" }}
              onClick={sendBack} disabled={!sendBackText.trim()}>
              <Send size={14} /> Send back to applicant
            </Button>
          </div>
        )}
        <div className="d-flex gap-2 mt-3">
          <Form.Control type="date" value={inspDate} onChange={(e: any) => setInspDate(e.target.value)} style={{ fontSize: ".82rem", background: "#0a0a0a", color: "#fff", borderColor: "#333" }} />
          <Button className="btn-mono flex-shrink-0" onClick={schedule}><Calendar size={14} /> Schedule inspection</Button>
        </div>
        {selected.status === "approved" && (
          <div className="mt-3">
            <Button className="btn-mono w-100" style={{ background: "#0a0", borderColor: "#0a0", color: "#fff" }}
              onClick={issueCertificate}>
              <Award size={14} /> Issue Sanction Letter (if not auto-generated)
            </Button>
            <p style={{ fontSize: ".72rem", color: "#c9c9c4" }} className="mt-1">
              Final Approve already generates the sanctioned letter automatically and pushes it to the
              applicant's Application panel. Use this only as a fallback.
            </p>
          </div>
        )}
      </Offcanvas.Body>
    </Offcanvas>
  );
}
