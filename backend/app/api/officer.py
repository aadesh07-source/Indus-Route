"""Officer endpoints: queue, AI pre-scrutiny summary, decisions,
AI-drafted clarifications (edit-before-send), inspection scheduling."""
from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import DecisionRequest, InspectionRequest, SignParameterRequest, CertificateRequest
from .. import db, config
from ..core.ai_service import draft_clarification, pre_scrutiny_summary
from ..core.readiness import sla_status
from ..core import green_channel
from .deps import require_roles, audit, notify

import time
import hashlib

router = APIRouter(prefix="/officer", tags=["officer"])


def _app_or_404(application_id: str) -> dict:
    app_row = db.query_one("SELECT * FROM applications WHERE id=?", (application_id,))
    if app_row is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return app_row


def _app_docs(application_id: str) -> list:
    rows = db.query("SELECT * FROM documents WHERE application_id=?", (application_id,))
    for r in rows:
        r["extracted_fields"] = db.jloads(r["extracted_fields"], {})
        r["validation_flags"] = db.jloads(r["validation_flags"], [])
    return rows


def _app_ctx(app_row: dict) -> dict:
    approval = db.query_one("SELECT * FROM approvals WHERE id=?", (app_row["approval_id"],))
    profile = db.query_one("SELECT * FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    cert = db.query_one(
        "SELECT certificate_no, type AS certificate_type, issued_at FROM certificates WHERE application_id=?",
        (app_row["id"],))
    return {
        "application": dict(app_row),
        "approval_name": approval["name"] if approval else "",
        "approval_code": approval["code"] if approval else "",
        "business_name": profile["name"] if profile else "",
        "readiness_score": app_row["readiness_score"],
        "documents": _app_docs(app_row["id"]),
        "certificate": dict(cert) if cert else None,
    }


@router.get("/queue")
def officer_queue(user: dict = Depends(require_roles("officer", "admin"))):
    """Assigned queue + unassigned submissions with readiness/SLA/attention."""
    rows = db.query(
        "SELECT a.*, ap.name AS approval_name, ap.code AS approval_code, "
        "b.name AS business_name, b.sector FROM applications a "
        "JOIN approvals ap ON a.approval_id=ap.id "
        "JOIN business_profiles b ON a.business_id=b.id "
        "WHERE a.status IN ('submitted','under_review','clarification_pending') "
        "ORDER BY a.submitted_at")
    queue = []
    for row in rows:
        entry = dict(row)
        entry["my_assignment"] = row["assigned_officer_id"] == user["id"]
        entry["documents"] = _app_docs(row["id"])
        # Attention level derived from readiness (rubric-based, not risk).
        score = entry.get("readiness_score", 0) or 0
        entry["attention"] = "low" if score >= 85 else ("medium" if score >= 60 else "high")
        entry["sla"] = sla_status(row)
        queue.append(entry)
    assigned = [q for q in queue if q["my_assignment"]]
    unassigned = [q for q in queue if q["assigned_officer_id"] is None]
    return {"assigned": assigned, "unassigned": unassigned,
            "note": ("Readiness % is a submission-completeness rubric; "
                     "attention is not a risk score.")}


@router.get("/queue/version")
def queue_version(user: dict = Depends(require_roles("officer", "admin"))):
    """Lightweight change signal for near-real-time polling (no WebSockets
    needed in the SQLite demo; Supabase Realtime replaces this in prod)."""
    row = db.query_one(
        "SELECT COUNT(*) AS n, COALESCE(MAX(created_at),'') AS latest "
        "FROM applications WHERE status IN "
        "('submitted','under_review','clarification_pending')")
    return {"version": "{}:{}".format(row["n"], row["latest"])}


@router.post("/applications/{application_id}/assign")
def assign_to_me(application_id: str,
                 user: dict = Depends(require_roles("officer", "admin"))):
    app_row = _app_or_404(application_id)
    if app_row["assigned_officer_id"] and app_row["assigned_officer_id"] != user["id"]:
        raise HTTPException(status_code=409, detail="Already assigned to another officer.")
    db.execute(
        "UPDATE applications SET assigned_officer_id=?, status=CASE WHEN status='submitted' "
        "THEN 'under_review' ELSE status END WHERE id=?",
        (user["id"], application_id))
    audit("application", application_id, user, "assign", "Officer claimed application.")
    profile = db.query_one("SELECT owner_id FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    if profile:
        notify(profile["owner_id"], "Officer Assigned",
               "An officer has started reviewing {}.".format(application_id),
               application_id=application_id)
    return {"status": "assigned", "officer_id": user["id"]}


@router.get("/applications/{application_id}/pre-scrutiny")
def pre_scrutiny(application_id: str,
                 user: dict = Depends(require_roles("officer", "admin"))):
    app_row = _app_or_404(application_id)
    ctx = _app_ctx(app_row)
    summary = pre_scrutiny_summary(ctx, ctx["documents"])

    # Deterministic one-click-readiness matrix (mirrors Green Channel logic
    # but for ANY approval type: every required doc present + 100% checks).
    approval = db.query_one("SELECT * FROM approvals WHERE id=?",
                            (app_row["approval_id"],))
    required = db.jloads(approval["required_documents"], []) if approval else []
    docs_by_type = {}
    for d in ctx["documents"]:
        docs_by_type.setdefault(d.get("type"), []).append(d)
    matrix, all_green = [], True
    for doc_type in required:
        candidates = docs_by_type.get(doc_type, [])
        if not candidates:
            matrix.append({"doc_type": doc_type, "present": False,
                           "passed": None, "state": "missing"})
            all_green = False
            continue
        best = max(candidates, key=lambda d: (d.get("checks_passed", 0),
                                              d.get("uploaded_at", "")))
        passed = (best.get("checks_total", 0) > 0
                  and best.get("checks_passed", 0) == best.get("checks_total", 0))
        matrix.append({"doc_type": doc_type, "present": True,
                       "checks_passed": best.get("checks_passed", 0),
                       "checks_total": best.get("checks_total", 0),
                       "state": "green" if passed else "failing"})
        if not passed:
            all_green = False
    open_clr = db.query_one(
        "SELECT id FROM clarification_requests WHERE application_id=? AND status='open'",
        (application_id,))
    if open_clr:
        all_green = False

    # ---- Per-parameter clearance analysis + officer sign-off state ----
    from ..core import digilocker
    profile_row = db.query_one(
        "SELECT owner_id, pan_hash, gst_hash FROM business_profiles WHERE id=?",
        (app_row["business_id"],))
    kyc = digilocker.latest_verified(profile_row["owner_id"]) if profile_row else {}
    signoffs = db.query(
        "SELECT param_key, officer_id, created_at FROM parameter_signoffs "
        "WHERE application_id=?", (application_id,))
    signed_map = {s["param_key"]: s for s in signoffs}
    parameters = []

    def add_param(key, label, state, analysis):
        s = signed_map.get(key)
        parameters.append({
            "param_key": key, "label": label,
            "state": state, "analysis": analysis,
            "signed": bool(s),
            "signed_by": s["officer_id"] if s else None,
            "signed_at": s["created_at"] if s else None,
        })

    kyc_ok = kyc.get("kyc_status") in ("verified", "applied")
    add_param(
        "identity_kyc", "Applicant identity & e-KYC",
        "green" if kyc_ok else "attention",
        ("DigiLocker e-KYC {} (consent ref {}).".format(
            kyc.get("kyc_status"), kyc.get("digilocker_ref", "-")))
        if kyc else
        "No DigiLocker e-KYC on file — identity is self-declared only.")

    for m in matrix:
        if m["state"] == "green":
            analysis = ("All {} deterministic checks passed ({}/{}).".format(
                m["checks_total"], m["checks_passed"], m["checks_total"]))
        elif m["state"] == "failing":
            analysis = ("Failing checks: {}/{} passed — see document matrix."
                        .format(m["checks_passed"], m["checks_total"]))
        else:
            analysis = "Document has not been uploaded yet."
        add_param("doc:{}".format(m["doc_type"]),
                  "Document: {}".format(m["doc_type"].replace("_", " ")),
                  m["state"], analysis)

    # PAN<->GSTIN cross-link (from the uploaded GST certificate's checks)
    pan_link = None
    for d in ctx["documents"]:
        if d.get("type") == "gst_certificate":
            for f in d.get("validation_flags", []):
                if f.get("check_id") == "gstin_pan_link":
                    pan_link = f
    if pan_link is not None:
        add_param("pan_gstin_link", "PAN <-> GSTIN cross-verification",
                  "green" if pan_link.get("passed") else "attention",
                  pan_link.get("reason", ""))
    else:
        add_param("pan_gstin_link", "PAN <-> GSTIN cross-verification",
                  "na", "No GST certificate required for this approval type.")

    readiness_100 = (app_row["readiness_score"] or 0) >= 100
    add_param("readiness_100", "Submission readiness 100%",
              "green" if readiness_100 else "attention",
              "Rubric-based readiness score: {}/100.".format(
                  app_row["readiness_score"] or 0))

    # 'na' parameters are auto-satisfied; 'green' ones need an officer tick;
    # 'attention' ones cannot be signed until the underlying issue is fixed.
    for p in parameters:
        if p["state"] == "na":
            p["signed"] = True
            p["auto"] = True
    unsigned = [p["label"] for p in parameters
                if p["state"] == "green" and not p["signed"]]

    # Auto-form provenance (AI/autofill generated, hash-bound).
    form = db.query_one(
        "SELECT filename, verification_code, source, sha256, generated_at, "
        "submitted_at FROM generated_forms WHERE application_id=? "
        "ORDER BY generated_at DESC LIMIT 1", (application_id,))

    return {
        "ai_summary": summary,          # AI suggestion (checklist, not verdict)
        "deterministic_data": {         # system facts
            "readiness_score": app_row["readiness_score"],
            "decision_source": app_row["decision_source"],
            "documents": ctx["documents"],
            "green_channel_eligible": bool(app_row["green_channel"]),
        },
        "one_click": {
            "all_green": all_green,
            "all_signed": len(unsigned) == 0 and all_green,
            "unsigned_count": len(unsigned),
            "unsigned": unsigned,
            "required_matrix": matrix,
            "readiness_100": readiness_100,
            "note": ("Approve parameters one by one; Final Approve unlocks only "
                     "when every parameter carries the officer's tick."),
        },
        "parameters": parameters,
        "form": dict(form) if form else None,
        "principle": "AI explains; rules and the officer decide.",
    }


@router.post("/applications/{application_id}/sign-parameter")
def sign_parameter(application_id: str, body: SignParameterRequest,
                   user: dict = Depends(require_roles("officer", "admin"))):
    """Officer approves ONE clearance parameter after reviewing its
    deterministic + AI analysis. Final approval needs every green parameter
    signed."""
    _app_or_404(application_id)
    pre = pre_scrutiny(application_id, user)  # full analysis (RBAC enforced)
    match = [p for p in pre["parameters"]
             if p["param_key"] == body.param_key.strip()]
    if not match:
        raise HTTPException(status_code=404, detail="Unknown parameter.")
    param = match[0]
    if param["state"] == "na":
        return {"param_key": body.param_key, "signed": True,
                "label": param["label"],
                "note": "Parameter not applicable — auto-satisfied."}
    if param["state"] != "green":
        raise HTTPException(
            status_code=409,
            detail="Parameter is not green (state: '{}') — the underlying "
                   "document/data must pass first.".format(param["state"]))
    db.execute(
        "INSERT INTO parameter_signoffs (id, application_id, officer_id, param_key, "
        "param_label, deterministic_state, note, created_at) VALUES (?,?,?,?,?,?,?,?) "
        "ON CONFLICT(application_id, param_key) DO UPDATE SET "
        "officer_id=excluded.officer_id, param_label=excluded.param_label, "
        "deterministic_state=excluded.deterministic_state, note=excluded.note, "
        "created_at=excluded.created_at",
        (db.new_id("par"), application_id, user["id"], body.param_key.strip(),
         param["label"], "green", body.note.strip(), db._now()))
    audit("parameter_signoff", application_id, user, "sign_parameter",
          "'{}' signed as verified.".format(param["label"]),
          {"param_key": body.param_key})
    remaining = [p["label"] for p in pre["parameters"]
                 if p["state"] == "green" and not p["signed"]
                 and p["param_key"] != body.param_key.strip()]
    return {"param_key": body.param_key, "signed": True,
            "label": param["label"],
            "remaining_parameters": remaining,
            "all_signed": len(remaining) == 0}


@router.post("/applications/{application_id}/draft-clarification")
def draft_clarification_endpoint(application_id: str,
                                 user: dict = Depends(require_roles("officer", "admin"))):
    """Returns an AI draft ONLY — never sent automatically (human-in-the-loop)."""
    app_row = _app_or_404(application_id)
    ctx = _app_ctx(app_row)
    issues = []
    for doc in ctx["documents"]:
        for flag in doc.get("validation_flags", []):
            if not flag.get("passed", False):
                issues.append("{} — {}: {}".format(
                    doc.get("label") or doc.get("type"),
                    flag.get("check_id"), flag.get("reason", "")))
    if not issues:
        issues.append("Officer-specified items (no failing automated checks).")
    return draft_clarification({
        "approval_name": ctx["approval_name"], "issues": issues[:10],
        "business_name": ctx["business_name"], "application_id": application_id,
    })


@router.post("/applications/{application_id}/draft-sendback")
def draft_sendback_endpoint(application_id: str,
                            user: dict = Depends(require_roles("officer", "admin"))):
    """AI-assisted summary of what the applicant must fix before resubmitting.
    Used as a starter text for the 'Send back' action — officer reviews & edits."""
    app_row = _app_or_404(application_id)
    ctx = _app_ctx(app_row)
    issues = []
    for doc in ctx["documents"]:
        for flag in doc.get("validation_flags", []):
            if not flag.get("passed", False):
                issues.append("{} — check '{}': {}".format(
                    doc.get("label") or doc.get("type"),
                    flag.get("check_id"), flag.get("reason", "")))
    profile = db.query_one(
        "SELECT sector, investment_size, employee_count, project_stage FROM "
        "business_profiles WHERE id=?", (app_row["business_id"],))
    if not issues:
        issues.append("Officer-specified items (no failing automated checks).")
    return draft_clarification({
        "approval_name": ctx["approval_name"], "issues": issues[:10],
        "business_name": ctx["business_name"], "application_id": application_id,
        "action": "send_back",
        "profile": profile,
    })


@router.post("/applications/{application_id}/decision")
def decision(application_id: str, body: DecisionRequest,
             user: dict = Depends(require_roles("officer", "admin"))):
    app_row = _app_or_404(application_id)
    if app_row["status"] in ("approved", "rejected", "provisionally_cleared"):
        raise HTTPException(status_code=409,
                            detail="A final decision already exists for this application.")
    profile = db.query_one("SELECT * FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    now = db._now()

    if body.action == "verify":
        db.execute("UPDATE applications SET assigned_officer_id=?, status='under_review' "
                   "WHERE id=?", (user["id"], application_id))
        audit("application", application_id, user, "verify", body.notes)
        return {"status": "under_review",
                "note": "Documents marked as verified by officer."}

    if body.action == "clarify":
        final_text = (body.clarification_text or "").strip() or body.notes.strip()
        if not final_text:
            raise HTTPException(
                status_code=422,
                detail="Provide clarification_text (officer-edited) or notes.")
        rid = db.new_id("clr")
        db.execute(
            "INSERT INTO clarification_requests (id, application_id, raised_by, "
            "ai_drafted_text, final_text, status, created_at) "
            "VALUES (?,?,?,?,?,'open',?)",
            (rid, application_id, user["id"],
             body.notes or "(officer-authored)", final_text, now))
        db.execute("UPDATE applications SET assigned_officer_id=?, "
                   "status='clarification_pending' WHERE id=?",
                   (user["id"], application_id))
        audit("clarification_request", rid, user, "raise_clarification",
              "AI-drafted letter edited and sent by officer.")
        if profile:
            notify(profile["owner_id"], "Clarification Requested",
                   final_text[:300], application_id=application_id,
                   sms_body="Clarification requested on application {}. Check portal."
                   .format(application_id[-8:]))
        return {"clarification_id": rid, "status": "clarification_pending",
                "ai_separation": {"ai_drafted_text": body.notes or "",
                                  "final_text": final_text}}

        # Send back — officer identifies issues, returns for corrections (AI-drafted).
    if body.action == "send_back":
        if not body.notes.strip():
            raise HTTPException(
                status_code=422,
                detail="Provide notes describing the corrections needed.")
        db.execute(
            "UPDATE applications SET status='returned', feedback=?, "
            "assigned_officer_id=? WHERE id=?",
            (body.notes.strip(), user["id"], application_id))
        audit("application", application_id, user, "send_back", body.notes.strip(),
              {"action": "send_back"})
        if profile:
            notify(profile["owner_id"], "Application Returned for Corrections",
                   body.notes.strip()[:300], application_id=application_id,
                   sms_body="Application {} returned for corrections.".format(
                       application_id[-8:]))
        return {"status": "returned", "decision_source": "human"}

    # Approve / Reject — ALWAYS officer-initiated (FR-18).
    if body.action == "approve":
        open_req = db.query_one(
            "SELECT id FROM clarification_requests WHERE application_id=? "
            "AND status='open'", (application_id,))
        if open_req:
            raise HTTPException(
                status_code=409,
                detail="An open clarification request must be resolved first.")
        # Parameter gate: every green parameter must be individually signed.
        pre = pre_scrutiny(application_id, user)
        unsigned = [p["label"] for p in pre["parameters"]
                    if p["state"] == "green" and not p["signed"]]
        if unsigned:
            raise HTTPException(
                status_code=409,
                detail="Approve each parameter first — {} remaining: {}".format(
                    len(unsigned), "; ".join(unsigned[:5])))
        new_status = "approved"
    else:
        new_status = "rejected"

    db.execute(
        "UPDATE applications SET status=?, assigned_officer_id=?, decision_source='human', "
        "decision_notes=?, decided_at=? WHERE id=?",
        (new_status, user["id"], body.notes.strip(), now, application_id))
    audit("application", application_id, user,
          "approve" if body.action == "approve" else "reject",
          body.notes or "(no notes)", {"action": body.action})
    sanction_letter = None
    if body.action == "approve":
        # Final approval instantly generates the sanction letter, which appears
        # in the applicant's Application panel below the form PDF.
        final_row = _app_or_404(application_id)
        sanction_letter = _issue_sanction_letter(final_row, user["id"])
    if profile:
        notify(profile["owner_id"],
               "Application {}".format(new_status.replace("_", " ").title()),
               body.notes or "Decision recorded.", application_id=application_id,
               sms_body="Application {} status: {}.".format(
                   application_id[-8:], new_status.replace("_", " ")))
    result = {"status": new_status, "decision_source": "human"}
    if body.action == "approve" and sanction_letter:
        result["sanction_letter"] = sanction_letter
    return result


@router.post("/applications/{application_id}/schedule-inspection")
def schedule_inspection(application_id: str, body: InspectionRequest,
                        user: dict = Depends(require_roles("officer", "admin"))):
    _app_or_404(application_id)
    ins_id = db.new_id("ins")
    db.execute(
        "INSERT INTO inspections (id, application_id, type, scheduled_date, status, "
        "coordinated_with, is_post_facto_audit, created_at) VALUES (?,?,?,?,?,?,0,?)",
        (ins_id, application_id, body.type.strip(), body.scheduled_date,
         "scheduled", db.jdumps(body.coordinated_with[:5]), db._now()))
    audit("inspection", ins_id, user, "schedule",
          "Inspection scheduled for {}.".format(body.scheduled_date))
    return {"inspection_id": ins_id, "status": "scheduled",
            "scheduled_date": body.scheduled_date}


@router.get("/green-channel/status")
def green_channel_status(user: dict = Depends(require_roles("officer", "admin"))):
    return {"enabled": green_channel.green_channel_enabled(),
            "rate_limit_per_day": config.GC_RATE_LIMIT_PER_DAY}


def _issue_sanction_letter(app_row: dict, officer_id: str,
                           certificate_type: str = "sanction_clearance") -> dict:
    """Generate and persist the sanction letter for an approved application.
    Idempotent: returns the existing letter if one was already issued."""
    existing = db.query_one(
        "SELECT id, certificate_no FROM certificates WHERE application_id=?",
        (app_row["id"],))
    if existing:
        return {"certificate_id": existing["id"],
                "certificate_no": existing["certificate_no"],
                "certificate_type": certificate_type,
                "already_issued": True}
    ctx = _app_ctx(app_row)
    from ..core import form_pdf
    ctx["certificate_type"] = certificate_type
    pdf_bytes = form_pdf.build_sanction_certificate(ctx)
    cert_id = db.new_id("cert")
    cert_no = "INDUS-SANCTION-{}".format(int(time.time()))
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    db.execute(
        "INSERT INTO certificates (id, application_id, business_id, certificate_no, "
        "type, issued_at, issuing_officer_id, verification_hash, form_data) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (cert_id, app_row["id"], app_row["business_id"], cert_no,
         certificate_type, db._now(), officer_id, sha256,
         db.jdumps({
             "applicant_name": ctx["business_name"],
             "approval_name": ctx["approval_name"],
             "approval_code": ctx["approval_code"],
             "sha256": sha256,
             "certificate_no": cert_no,
         })))
    audit("certificate", cert_id, {"id": officer_id}, "issue",
          "Sanction letter generated for application {}.",
          {"application_id": app_row["id"], "type": certificate_type})
    profile = db.query_one(
        "SELECT owner_id FROM business_profiles WHERE id=?",
        (app_row["business_id"],))
    if profile:
        notify(profile["owner_id"], "Sanction Letter Issued",
               "Your sanctioned clearance letter is ready — download it from "
               "your Application panel.",
               application_id=app_row["id"],
               sms_body="Sanction letter issued. Download from your portal.")
    return {"certificate_id": cert_id, "certificate_no": cert_no,
            "certificate_type": certificate_type}


@router.post("/applications/{application_id}/issue-certificate")
def issue_certificate(application_id: str,
                      body: CertificateRequest,
                      user: dict = Depends(require_roles("officer", "admin"))):
    """Officer issues the sanction letter after final approval (idempotent)."""
    app_row = _app_or_404(application_id)
    if app_row["status"] != "approved":
        raise HTTPException(
            status_code=409,
            detail="Application must be approved before the sanction letter "
                   "can be generated.")
    result = _issue_sanction_letter(app_row, user["id"], body.certificate_type)
    return result


@router.get("/applications/{application_id}/certificate")
def download_certificate(application_id: str,
                          user: dict = Depends(require_roles("officer", "admin"))):
    """Officer downloads the sanction certificate PDF."""
    cert = db.query_one(
        "SELECT c.* FROM certificates c WHERE c.application_id=?",
        (application_id,))
    if cert is None:
        raise HTTPException(
            status_code=404,
            detail="No certificate has been issued for this application.")
    app_row = _app_or_404(application_id)
    ctx = _app_ctx(app_row)
    from ..core import form_pdf
    form_data = db.jloads(cert["form_data"], {})
    ctx.update({
        "certificate_no": cert["certificate_no"],
        "certificate_type": cert["type"],
        "issued_at": cert["issued_at"],
        "issued_by": cert["issuing_officer_id"],
    })
    pdf_bytes = form_pdf.build_sanction_certificate(ctx)
    from fastapi.responses import StreamingResponse
    import io
    buf = io.BytesIO(pdf_bytes)
    headers = {
        "Content-Disposition": 'inline; filename="INDUS_ROUTE_SANCTION_CERTIFICATE_{}.pdf"'.format(
            cert["certificate_no"])
    }
    return StreamingResponse(buf, media_type="application/pdf", headers=headers)


@router.get("/certificates/verify/{certificate_no}")
def verify_certificate(certificate_no: str):
    """Verify a sanction certificate's authenticity (public, no PII)."""
    cert = db.query_one(
        "SELECT c.certificate_no, c.type AS certificate_type, c.issued_at, "
        "c.verification_hash FROM certificates c WHERE c.certificate_no=?",
        (certificate_no.strip(),))
    if cert is None:
        return {"valid": False, "note": "No certificate found for this number."}
    return {
        "valid": True,
        "certificate_no": cert["certificate_no"],
        "certificate_type": cert["certificate_type"],
        "issued_at": cert["issued_at"],
        "sha256_prefix": cert["verification_hash"][:16],
        "note": "Verify PDF integrity hash matches the value recorded at issuance."
    }


