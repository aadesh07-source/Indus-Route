"""Application endpoints: create, readiness, submit (incl. Green Channel),
auto-generated PDF forms, clarifications, grievances, schemes, Q&A, notifications."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..models.schemas import (CreateApplicationRequest, RespondClarificationRequest,
                              GrievanceRequest)
from .. import db, config
from ..core.readiness import compute_readiness, sla_deadline_for, sla_status
from ..core import green_channel, digilocker, form_pdf
from ..core.rule_engine import evaluate_profile
from ..core.ai_service import answer_regulatory_question
from .deps import (get_current_user, get_own_profile, load_profile_dict,
                   audit, notify)

router = APIRouter(tags=["applications"])


def _load_application(application_id: str) -> dict:
    app_row = db.query_one("SELECT * FROM applications WHERE id=?", (application_id,))
    if app_row is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return app_row


def _assert_can_view(app_row: dict, user: dict) -> None:
    profile = db.query_one("SELECT owner_id FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    is_owner = profile and profile["owner_id"] == user["id"]
    is_official = user["role"] in ("officer", "admin")
    if not (is_owner or is_official or app_row.get("assigned_officer_id") == user["id"]):
        raise HTTPException(status_code=403,
                            detail="You do not have access to this application.")


def _app_documents(application_id: str) -> list:
    rows = db.query("SELECT * FROM documents WHERE application_id=? ORDER BY uploaded_at",
                    (application_id,))
    for r in rows:
        r["extracted_fields"] = db.jloads(r["extracted_fields"], {})
        r["validation_flags"] = db.jloads(r["validation_flags"], [])
    return rows


def _app_view(app_row: dict, with_docs: bool = False) -> dict:
    approval = db.query_one("SELECT * FROM approvals WHERE id=?", (app_row["approval_id"],))
    docs_stats = db.query_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(checks_passed),0) AS p, "
        "COALESCE(SUM(checks_total),0) AS t FROM documents WHERE application_id=?",
        (app_row["id"],))
    view = {
        "id": app_row["id"], "status": app_row["status"],
        "business_id": app_row["business_id"], "approval_id": app_row["approval_id"],
        "approval_name": approval["name"] if approval else "",
        "approval_code": approval["code"] if approval else "",
        "department": approval["department"] if approval else "",
        "sla_days": approval["sla_days"] if approval else None,
        "submitted_at": app_row["submitted_at"], "sla_deadline": app_row["sla_deadline"],
        "assigned_officer_id": app_row["assigned_officer_id"],
        "decision_source": app_row["decision_source"],
        "decision_notes": app_row["decision_notes"], "decided_at": app_row["decided_at"],
        "readiness_score": app_row["readiness_score"],
        "green_channel": bool(app_row["green_channel"]),
        "provisional_certificate": db.jloads(app_row["provisional_certificate"], None),
        "feedback": app_row.get("feedback", ""),
        "selected_schemes": db.jloads(app_row.get("selected_schemes"), []),
        "sla": sla_status(app_row),
        "docs_pending": (docs_stats["n"] == 0 or docs_stats["p"] < docs_stats["t"]),
        "docs_passed": docs_stats["p"], "docs_total": docs_stats["t"],
        "docs_count": docs_stats["n"],
        "created_at": app_row["created_at"],
    }
    cert = db.query_one(
        "SELECT certificate_no, type AS certificate_type, issued_at FROM certificates "
        "WHERE application_id=?", (app_row["id"],))
    view["certificate"] = dict(cert) if cert else None
    if with_docs:
        view["documents"] = _app_documents(app_row["id"])
        view["clarifications"] = db.query(
            "SELECT * FROM clarification_requests WHERE application_id=? ORDER BY created_at",
            (app_row["id"],))
        view["schemes_selected"] = db.query(
            "SELECT scheme_id, selected_at FROM application_schemes "
            "WHERE application_id=? ORDER BY selected_at", (app_row["id"],))
    return view


@router.post("/applications", status_code=201)
def create_application(body: CreateApplicationRequest,
                       user: dict = Depends(get_current_user)):
    profile = get_own_profile(user)
    # Look up the approval within the applicant's own sector — this avoids
    # ambiguity when the same approval code exists in multiple sector rule tables.
    approval = db.query_one(
        "SELECT * FROM approvals WHERE (id=? OR code=?) AND sector=?",
        (body.approval_id, body.approval_id, profile["sector"]))
    if approval is None:
        valid = db.query(
            "SELECT code FROM approvals WHERE sector=? ORDER BY code", (profile["sector"],))
        codes = ", ".join(r["code"] for r in valid)
        raise HTTPException(
            status_code=404,
            detail="Unknown approval '{}' for sector '{}'. Valid approvals: {}".format(
                body.approval_id, profile["sector"], codes or "(none)"))
    if approval["sector"] != profile["sector"]:
        raise HTTPException(
            status_code=422,
            detail="Approval '{}' belongs to sector '{}', but your profile sector "
            "is '{}'.".format(approval["code"], approval["sector"], profile["sector"]))
    app_id = db.new_id("app")
    db.execute(
        "INSERT INTO applications (id, business_id, approval_id, status, created_at) "
        "VALUES (?,?,?,'draft',?)",
        (app_id, profile["id"], approval["id"], db._now()))
    audit("application", app_id, user, "create",
          "Draft application created from the rule-engine checklist.")
    return {"application_id": app_id,
            "application": _app_view(_load_application(app_id))}


@router.get("/applications")
def my_applications(user: dict = Depends(get_current_user)):
    if user["role"] in ("officer", "admin"):
        rows = db.query(
            "SELECT a.*, ap.name AS approval_name, ap.code AS approval_code, "
            "ap.department, ap.sla_days, "
            "(SELECT COUNT(*) FROM documents d WHERE d.application_id=a.id) AS docs_count, "
            "(SELECT COALESCE(SUM(d.checks_passed),0) FROM documents d WHERE d.application_id=a.id) AS docs_passed, "
            "(SELECT COALESCE(SUM(d.checks_total),0) FROM documents d WHERE d.application_id=a.id) AS docs_total "
            "FROM applications a JOIN approvals ap ON a.approval_id=ap.id ORDER BY a.created_at DESC")
    else:
        profile = get_own_profile(user)
        rows = db.query(
            "SELECT a.*, ap.name AS approval_name, ap.code AS approval_code, "
            "ap.department, ap.sla_days, "
            "(SELECT COUNT(*) FROM documents d WHERE d.application_id=a.id) AS docs_count, "
            "(SELECT COALESCE(SUM(d.checks_passed),0) FROM documents d WHERE d.application_id=a.id) AS docs_passed, "
            "(SELECT COALESCE(SUM(d.checks_total),0) FROM documents d WHERE d.application_id=a.id) AS docs_total "
            "FROM applications a JOIN approvals ap ON a.approval_id=ap.id "
            "WHERE a.business_id=? ORDER BY a.created_at DESC", (profile["id"],))
    if not rows:
        return {"applications": []}
    app_ids = [r["id"] for r in rows]
    doc_counts = db.query(
        "SELECT application_id, COUNT(*) AS docs_count, "
        "COALESCE(SUM(checks_passed),0) AS docs_passed, "
        "COALESCE(SUM(checks_total),0) AS docs_total FROM documents "
        "WHERE application_id IN ({}) GROUP BY application_id".format(
            ",".join("?" * len(app_ids))), app_ids) if rows else []
    cert_rows = db.query(
        "SELECT application_id, certificate_no, type AS certificate_type, issued_at "
        "FROM certificates WHERE application_id IN ({})".format(
            ",".join("?" * len(app_ids))), app_ids) if rows else []
    certs_by_app = {r["application_id"]: r for r in cert_rows}
    docs_by_app = {r["application_id"]: r for r in doc_counts}
    out = []
    for r in rows:
        d = dict(r)
        dc = docs_by_app.get(r["id"], {})
        d["docs_count"] = dc.get("docs_count", 0)
        d["docs_passed"] = dc.get("docs_passed", 0)
        d["docs_total"] = dc.get("docs_total", 0)
        d["docs_pending"] = (d["docs_count"] == 0 or d["docs_passed"] < d["docs_total"])
        cert = certs_by_app.get(r["id"])
        d["certificate"] = dict(cert) if cert else None
        d["feedback"] = r.get("feedback", "")
        d["selected_schemes"] = db.jloads(r.get("selected_schemes"), [])
        out.append(d)
    return {"applications": out}


@router.get("/applications/{application_id}")
def get_application(application_id: str, user: dict = Depends(get_current_user)):
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    view = _app_view(app_row, with_docs=True)
    inspections = db.query(
        "SELECT * FROM inspections WHERE application_id=? ORDER BY created_at",
        (application_id,))
    return {"application": view, "inspections": inspections}


@router.get("/applications/{application_id}/readiness")
def application_readiness(application_id: str, user: dict = Depends(get_current_user)):
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    profile = db.query_one("SELECT * FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    approval = dict(db.query_one("SELECT * FROM approvals WHERE id=?",
                                 (app_row["approval_id"],)))
    documents = _app_documents(application_id)
    result = compute_readiness(load_profile_dict(profile), _approval_dict(approval), documents)
    db.execute("UPDATE applications SET readiness_score=?, readiness_breakdown=? WHERE id=?",
               (result["score"], db.jdumps(result["breakdown"]), application_id))
    return result


def _approval_dict(approval: dict) -> dict:
    """Approval row with JSON columns decoded for the readiness rubric."""
    d = dict(approval)
    d["required_documents"] = db.jloads(d.get("required_documents"), [])
    d["dependency_ids"] = db.jloads(d.get("dependency_ids"), [])
    d["green_channel_eligible"] = bool(d.get("green_channel_eligible"))
    return d


def _perform_submit(app_row: dict, user: dict, source: str) -> dict:
    """Shared submission path (manual submit and auto-form submit)."""
    profile = db.query_one("SELECT * FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    approval = _approval_dict(db.query_one(
        "SELECT * FROM approvals WHERE id=?", (app_row["approval_id"],)))
    documents = _app_documents(app_row["id"])
    readiness = compute_readiness(load_profile_dict(profile), approval, documents)

    now = db._now()
    deadline = sla_deadline_for(approval["sla_days"])

    # Persist readiness on every submission path (incl. Green Channel).
    db.execute(
        "UPDATE applications SET readiness_score=?, readiness_breakdown=? WHERE id=?",
        (readiness["score"], db.jdumps(readiness["breakdown"]), app_row["id"]))

    # Green Channel extension: deterministic auto-issuance attempt.
    gc = green_channel.attempt_green_channel(dict(app_row), approval, documents)

    if gc["issued"]:
        notify(profile["owner_id"], "Application Provisionally Cleared",
               gc["certificate"]["certificate_no"] +
               " issued. Post-facto audit is mandatory.",
               application_id=app_row["id"],
               sms_body="Provisional permit issued - subject to audit.")
    else:
        db.execute(
            "UPDATE applications SET status='submitted', submitted_at=?, "
            "sla_deadline=?, readiness_score=?, readiness_breakdown=? WHERE id=?",
            (now, deadline, readiness["score"], db.jdumps(readiness["breakdown"]),
             app_row["id"]))
        # Instant dispatch: every officer is notified immediately.
        for off in db.query("SELECT id FROM users WHERE role='officer'"):
            notify(off["id"], "New Application Submitted",
                   "{} ({}) is awaiting assignment.".format(
                       app_row["id"], approval["name"]), application_id=app_row["id"])
        notify(profile["owner_id"], "Application Submitted",
               "Your application is in the officer queue. SLA deadline: {}".format(
                   deadline[:10]), application_id=app_row["id"])

    audit("application", app_row["id"], user, "submit",
          "Submitted via {}. Readiness {}%. Green channel: {}".format(
              source, readiness["score"], "issued" if gc["issued"] else gc["reason"]),
          {"green_channel_issued": gc["issued"], "source": source})
    app_row = _load_application(app_row["id"])
    return {"application": _app_view(app_row), "readiness": readiness,
            "green_channel": gc}


@router.post("/applications/{application_id}/submit")
def submit_application(application_id: str, user: dict = Depends(get_current_user)):
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    if app_row["status"] not in ("draft", "clarification_pending", "returned"):
        raise HTTPException(
            status_code=409,
            detail="Application cannot be submitted from status '{}'.".format(
                app_row["status"]))
    if app_row["status"] == "returned":
        db.execute(
            "UPDATE applications SET status='draft', feedback='' WHERE id=?",
            (application_id,))
        app_row = _load_application(application_id)
    return _perform_submit(app_row, user, "manual submission")



def _build_and_store_form(app_row: dict, user: dict) -> dict:
    """Core form-generation logic shared by the generate + download endpoints."""
    profile = db.query_one("SELECT * FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    approval = _approval_dict(db.query_one(
        "SELECT * FROM approvals WHERE id=?", (app_row["approval_id"],)))
    documents = _app_documents(app_row["id"])
    checklist = evaluate_profile(load_profile_dict(profile))
    kyc = digilocker.latest_verified(profile["owner_id"])
    applicant = db.query_one("SELECT name FROM users WHERE id=?",
                             (profile["owner_id"],))
    selected_scheme_ids = db.jloads(app_row.get("selected_schemes"), [])
    schemes_ctx = []
    if selected_scheme_ids:
        placeholders = ",".join("?" * len(selected_scheme_ids))
        rows = db.query(
            "SELECT id, name, description, benefits FROM schemes "
            "WHERE id IN ({})".format(placeholders), selected_scheme_ids)
        schemes_ctx = [dict(r) for r in rows]

    identity = form_pdf.new_form_identity(app_row["id"], app_row["business_id"])
    pdf_bytes = form_pdf.build_application_pdf({
        "form_no": identity["form_no"],
        "generated_at": identity["generated_at"],
        "verification_code": identity["verification_code"],
        "sha256": identity["sha256"],
        "profile": profile, "approval": approval, "checklist": checklist,
        "documents": documents, "kyc": kyc,
        "selected_schemes": schemes_ctx,
        "applicant_name": applicant["name"] if applicant else "",
    })

    form_id = db.new_id("frm")
    forms_dir = config.DATA_DIR / "forms"
    forms_dir.mkdir(parents=True, exist_ok=True)
    filename = "UAF-{}.pdf".format(identity["verification_code"])
    file_path = forms_dir / "{}.pdf".format(form_id)
    file_path.write_bytes(pdf_bytes)

    db.execute(
        "INSERT INTO generated_forms (id, application_id, business_id, filename, "
        "file_ref, sha256, verification_code, source, checklist_snapshot, "
        "generated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (form_id, app_row["id"], app_row["business_id"], filename,
         str(file_path), identity["sha256"], identity["verification_code"],
         "kyc-autofill" if kyc else "profile-autofill",
         db.jdumps({"sector": checklist.get("sector"),
                    "approvals": [a["code"] for a in checklist.get("approvals", [])],
                    "known": checklist.get("known")}),
         identity["generated_at"]))
    audit("generated_form", form_id, user, "generate",
          "Unified Application Form PDF generated ({} source).".format(
              "e-KYC autofill" if kyc else "profile autofill"))
    return {
        "form_id": form_id, "filename": filename,
        "verification_code": identity["verification_code"],
        "sha256": identity["sha256"],
        "kyc_bound": bool(kyc),
        "download_url": "/api/applications/{}/form.pdf".format(app_row["id"]),
        "size_bytes": len(pdf_bytes),
    }


@router.post("/applications/{application_id}/generate-form")
def generate_form(application_id: str, user: dict = Depends(get_current_user)):
    """Auto-generate the Unified Application Form PDF from e-KYC data,
    the business profile, the rule-engine checklist and document validation."""
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    return _build_and_store_form(app_row, user)


@router.get("/applications/{application_id}/form.pdf")
def download_form(application_id: str, user: dict = Depends(get_current_user)):
    """Serve the latest form PDF; auto-generate one on demand if missing
    (so the download button always works, at any application stage)."""
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    form = db.query_one(
        "SELECT * FROM generated_forms WHERE application_id=? "
        "ORDER BY generated_at DESC LIMIT 1", (application_id,))
    if form is None:
        _build_and_store_form(app_row, user)
        form = db.query_one(
            "SELECT * FROM generated_forms WHERE application_id=? "
            "ORDER BY generated_at DESC LIMIT 1", (application_id,))
    try:
        data = (config.DATA_DIR / "forms" / "{}.pdf".format(form["id"])).read_bytes()
    except OSError:
        raise HTTPException(status_code=410, detail="Stored form file is missing.")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition":
                             "attachment; filename={}".format(form["filename"])})


@router.post("/applications/{application_id}/clarifications/{request_id}/respond")
def respond_clarification(application_id: str, request_id: str,
                          body: RespondClarificationRequest,
                          user: dict = Depends(get_current_user)):
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    req = db.query_one(
        "SELECT * FROM clarification_requests WHERE id=? AND application_id=?",
        (request_id, application_id))
    if req is None:
        raise HTTPException(status_code=404, detail="Clarification request not found.")
    if req["status"] != "open":
        raise HTTPException(status_code=409, detail="Clarification is already closed.")
    db.execute(
        "UPDATE clarification_requests SET applicant_response=?, status='responded', "
        "responded_at=? WHERE id=?", (body.response.strip(), db._now(), request_id))
    db.execute("UPDATE applications SET status='under_review' WHERE id=?",
               (application_id,))
    audit("clarification_request", request_id, user, "respond",
          "Applicant responded to clarification.")
    notify(req["raised_by"], "Clarification Response Received",
           "Response received on application {}.".format(application_id),
           application_id=application_id)
    return {"status": "responded"}


@router.post("/grievances", status_code=201)
def raise_grievance(body: GrievanceRequest, user: dict = Depends(get_current_user)):
    if body.application_id:
        _assert_can_view(_load_application(body.application_id), user)
    gid = db.new_id("grv")
    db.execute(
        "INSERT INTO grievances (id, application_id, user_id, reason, description, "
        "escalation_level, status, created_at) VALUES (?,?,?,?,?,0,'open',?)",
        (gid, body.application_id or "", user["id"], body.reason.strip(),
         body.description.strip(), db._now()))
    audit("grievance", gid, user, "raise", body.reason)
    return {"grievance_id": gid, "status": "open"}


@router.get("/grievances")
def my_grievances(user: dict = Depends(get_current_user)):
    if user["role"] in ("officer", "admin"):
        rows = db.query("SELECT * FROM grievances ORDER BY created_at DESC")
    else:
        rows = db.query(
            "SELECT * FROM grievances WHERE user_id=? ORDER BY created_at DESC",
            (user["id"],))
    return {"grievances": rows}


@router.get("/schemes/recommendations")
def scheme_recommendations(user: dict = Depends(get_current_user)):
    from ..core.rule_engine import _eval_condition

    SECTOR_CATEGORY = {
        "food_processing": "Agro & Food Processing",
        "textiles": "Textiles, Apparel & Technical Textiles",
        "chemicals": "Chemicals & Industrial Safety",
        "distillery": "Distilleries & Breweries",
        "pharma": "Pharmaceuticals, APIs & Medical Devices",
        "automotive": "Automobile, EV & Heavy Engineering",
        "electronics": "Electronics System Design & Manufacturing (ESDM)",
        "logistics": "Logistics, Warehousing & Cold Chain",
        "energy": "Renewable Energy, Biofuels & Green Manufacturing",
    }
    UNIVERSAL = "Universal Baseline — PSI / MIISP Package of Incentives"
    UNIVERSAL_IDS = {"psi_ips", "psi_stamp", "psi_interest", "psi_power",
                     "sch_msme", "sch_mega"}

    def _category(scheme_id: str, conds) -> str:
        if scheme_id in UNIVERSAL_IDS:
            return UNIVERSAL
        for c in conds:
            if c.get("field") == "sector":
                vals = c.get("value")
                vals = vals if isinstance(vals, list) else [vals]
                if vals:
                    return SECTOR_CATEGORY.get(
                        str(vals[0]), str(vals[0]).replace("_", " ").title())
        return UNIVERSAL

    profile = get_own_profile(user)
    p = load_profile_dict(profile)
    schemes = db.query("SELECT * FROM schemes")
    eligible, others = [], []
    for scheme in schemes:
        conditions = db.jloads(scheme["eligibility"], [])
        reasons = []
        for cond in conditions:
            if not _eval_condition(cond, p):
                reasons.append("Field '{}' did not meet the condition.".format(
                    cond.get("field")))
        category = _category(scheme["id"], conditions)
        if not reasons:
            eligible.append({"id": scheme["id"], "name": scheme["name"],
                             "description": scheme["description"],
                             "benefits": scheme["benefits"],
                             "category": category,
                             "explanation": "All eligibility rules matched your profile."})
        else:
            others.append({"id": scheme["id"], "name": scheme["name"],
                           "eligible": False, "category": category,
                           "explanation": "; ".join(reasons)})
    return {"eligible": eligible, "others": others,
            "note": "Rule-based eligibility only — advisory, not a scheme guarantee."}


@router.get("/qa/ask")
def regulatory_qa(q: str, user: dict = Depends(get_current_user)):
    return answer_regulatory_question(q)


@router.get("/notifications")
def my_notifications(user: dict = Depends(get_current_user)):
    rows = db.query(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
        (user["id"],))
    return {"notifications": rows}




@router.post("/applications/{application_id}/submit-form")
def submit_with_form(application_id: str, user: dict = Depends(get_current_user)):
    """Submit using the auto-generated form -> instant dispatch to officers."""
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    if app_row["status"] not in ("draft", "clarification_pending", "returned"):
        raise HTTPException(
            status_code=409,
            detail="Application cannot be submitted from status '{}'.".format(
                app_row["status"]))
    if app_row["status"] == "returned":
        db.execute(
            "UPDATE applications SET status='draft', feedback='' WHERE id=?",
            (application_id,))
        app_row = _load_application(application_id)
    form = db.query_one(
        "SELECT id, verification_code FROM generated_forms WHERE application_id=? "
        "ORDER BY generated_at DESC LIMIT 1", (application_id,))
    if form is None:
        raise HTTPException(status_code=422,
                            detail="Generate the Unified Application Form first.")
    db.execute("UPDATE generated_forms SET submitted_at=? WHERE id=?",
               (db._now(), form["id"]))
    result = _perform_submit(app_row, user,
                             "auto-generated form {}".format(form["verification_code"]))
    result["form_verification_code"] = form["verification_code"]
    result["dispatched"] = ("Instant dispatch: application is now visible in "
                            "the officer portal.")
    return result


@router.get("/forms/verify/{verification_code}")
def verify_form(verification_code: str):
    """Public tamper-evidence check (QR / verification code). No PII returned."""
    form = db.query_one(
        "SELECT * FROM generated_forms WHERE verification_code=?",
        (verification_code.strip().upper(),))
    if form is None:
        return {"valid": False,
                "note": "No form found for this verification code."}
    return {"valid": True, "form_no": form["filename"].replace(".pdf", ""),
            "generated_at": form["generated_at"],
            "submitted": bool(form["submitted_at"]),
            "sha256_prefix": form["sha256"][:16],
            "note": ("Cryptographically bound to its generation time; any edit "
                     "to the PDF invalidates the recorded hash.")}


@router.post("/applications/{application_id}/schemes")
def update_selected_schemes(application_id: str, body: dict,
                            user: dict = Depends(get_current_user)):
    """Persist the applicant's scheme selections for this application."""
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    if app_row["status"] not in ("draft", "clarification_pending", "returned"):
        raise HTTPException(
            status_code=409,
            detail="Schemes can only be edited while the application is in "
                   "draft/clarification/returned status (current: '{}').".format(
                       app_row["status"]))
    scheme_ids = body.get("scheme_ids") or []
    if not isinstance(scheme_ids, list):
        raise HTTPException(status_code=422, detail="scheme_ids must be a list.")
    valid = {r["id"] for r in db.query("SELECT id FROM schemes")}
    scheme_ids = [s for s in scheme_ids if s in valid]
    db.execute("DELETE FROM application_schemes WHERE application_id=?",
               (application_id,))
    if scheme_ids:
        db.executemany(
            "INSERT INTO application_schemes (id, application_id, scheme_id, "
            "selected_at) VALUES (?,?,?,?)",
            [(db.new_id("aps"), application_id, s, db._now()) for s in scheme_ids])
    db.execute("UPDATE applications SET selected_schemes=? WHERE id=?",
               (db.jdumps(scheme_ids), application_id))
    audit("application", application_id, user, "schemes_selected",
          "{} scheme(s) selected.".format(len(scheme_ids)),
          {"scheme_ids": scheme_ids})
    return {"selected_schemes": scheme_ids, "count": len(scheme_ids)}


@router.post("/applications/{application_id}/resubmit")
def resubmit_application(application_id: str, body: dict = None,
                          user: dict = Depends(get_current_user)):
    """Flip a 'returned' application back to draft and submit it again."""
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    if app_row["status"] != "returned":
        raise HTTPException(
            status_code=409,
            detail="Only applications in 'returned' status can be resubmitted "
                   "(current: '{}').".format(app_row["status"]))
    db.execute(
        "UPDATE applications SET status='draft', feedback='', decided_at=NULL "
        "WHERE id=?", (application_id,))
    audit("application", application_id, user, "resubmit_after_return",
          "Applicant re-submitted after officer returned for corrections.")
    return _perform_submit(_load_application(application_id), user,
                           "resubmit after return")


@router.get("/applications/{application_id}/certificate.pdf")
def applicant_download_certificate(application_id: str,
                                   user: dict = Depends(get_current_user)):
    """Applicant-side download of the sanction clearance certificate."""
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    if app_row["status"] != "approved":
        raise HTTPException(
            status_code=409,
            detail="Certificate is only available once the application is "
                   "approved (current: '{}').".format(app_row["status"]))
    cert = db.query_one(
        "SELECT *, type AS certificate_type FROM certificates WHERE application_id=?",
        (application_id,))
    if cert is None:
        raise HTTPException(status_code=404,
                            detail="No certificate has been issued yet.")
    from ..core import form_pdf
    profile = db.query_one("SELECT * FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    approval = db.query_one("SELECT * FROM approvals WHERE id=?",
                            (app_row["approval_id"],))
    applicant = db.query_one("SELECT name FROM users WHERE id=?",
                             (profile["owner_id"],)) if profile else None
    cert_ctx = {
        "app_id": app_row["id"],
        "application_id": app_row["id"],
        "business_name": profile["name"] if profile else "",
        "sector": (profile["sector"] if profile else "").replace("_", " ").title(),
        "approval_name": approval["name"] if approval else "",
        "approval_code": approval["code"] if approval else "",
        "department": approval["department"] if approval else "",
        "applicant_name": applicant["name"] if applicant else "",
        "authorized_person": profile["authorized_person"] if profile else "",
        "location": "{}, {}".format(
            (profile["district"] or "") if profile else "",
            (profile["industrial_zone"] or "") if profile else ""),
        "submitted_at": app_row["submitted_at"] or app_row["created_at"],
        "approved_at": app_row["decided_at"] or cert["issued_at"],
        "officer_name": "",
        "certificate_no": cert["certificate_no"],
        "certificate_type": cert["certificate_type"],
        "certificate_code": cert["verification_hash"][:16].upper(),
        "issued_at": cert["issued_at"],
        "generated_at": db._now(),
        "clearances": [
            "{} - {} (Department: {})".format(
                approval["code"] if approval else "", approval["name"] if approval else "",
                approval["department"] if approval else ""),
        ],
    }
    pdf_bytes = form_pdf.build_sanction_certificate(cert_ctx)
    from fastapi.responses import Response
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=IndusRoute-SANCTION-{}.pdf".format(
            cert["certificate_no"])})


@router.post("/applications/{application_id}/auto-fill-from-data")
def auto_fill_from_data(application_id: str,
                        user: dict = Depends(get_current_user)):
    """Aggregate every data source (profile + KYC + selected schemes + uploaded
    documents + checklist approvals) into the auto-generated UAF PDF.
    Called by the applicant immediately before submitting."""
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    if app_row["status"] not in ("draft", "clarification_pending", "returned"):
        raise HTTPException(
            status_code=409,
            detail="Auto-fill runs only for draft/clarification/returned "
                   "applications (current: '{}').".format(app_row["status"]))
    profile = db.query_one("SELECT * FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    kyc = digilocker.latest_verified(profile["owner_id"]) if profile else {}
    documents = _app_documents(app_row["id"])
    checklist = evaluate_profile(load_profile_dict(profile))
    return {
        "auto_filled": True,
        "sources": {
            "profile_filled": bool(profile and profile.get("name")),
            "kyc_bound": bool(kyc and kyc.get("kyc_status") in ("verified", "applied")),
            "documents_uploaded": len(documents),
            "documents_passing": sum(1 for d in documents
                                     if d.get("checks_passed") == d.get("checks_total")
                                     and d.get("checks_total", 0) > 0),
            "schemes_selected": len(db.jloads(app_row.get("selected_schemes"), [])),
            "approvals_in_checklist": len(checklist.get("approvals", [])),
        },
        "form": _build_and_store_form(app_row, user),
    }
