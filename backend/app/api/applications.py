"""Application endpoints: create, readiness, submit (incl. Green Channel),
clarifications, grievances, scheme recommendations, RAG Q&A, notifications."""
from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import (CreateApplicationRequest, RespondClarificationRequest,
                              GrievanceRequest)
from .. import db
from ..core.readiness import compute_readiness, sla_deadline_for, sla_status
from ..core import green_channel
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
        "sla": sla_status(app_row),
        "created_at": app_row["created_at"],
    }
    if with_docs:
        view["documents"] = _app_documents(app_row["id"])
    return view


@router.post("/applications", status_code=201)
def create_application(body: CreateApplicationRequest,
                       user: dict = Depends(get_current_user)):
    profile = get_own_profile(user)
    approval = db.query_one("SELECT * FROM approvals WHERE id=? OR code=?",
                            (body.approval_id, body.approval_id))
    if approval is None:
        raise HTTPException(status_code=404,
                            detail="Unknown approval '{}'.".format(body.approval_id))
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
            "ap.department, ap.sla_days FROM applications a "
            "JOIN approvals ap ON a.approval_id=ap.id ORDER BY a.created_at DESC")
    else:
        profile = get_own_profile(user)
        rows = db.query(
            "SELECT a.*, ap.name AS approval_name, ap.code AS approval_code, "
            "ap.department, ap.sla_days FROM applications a "
            "JOIN approvals ap ON a.approval_id=ap.id WHERE a.business_id=? "
            "ORDER BY a.created_at DESC", (profile["id"],))
    return {"applications": [dict(r) for r in rows]}


@router.get("/applications/{application_id}")
def get_application(application_id: str, user: dict = Depends(get_current_user)):
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    view = _app_view(app_row, with_docs=True)
    clarifications = db.query(
        "SELECT * FROM clarification_requests WHERE application_id=? ORDER BY created_at",
        (application_id,))
    inspections = db.query(
        "SELECT * FROM inspections WHERE application_id=? ORDER BY created_at",
        (application_id,))
    return {"application": view, "clarifications": clarifications,
            "inspections": inspections}


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


@router.post("/applications/{application_id}/submit")
def submit_application(application_id: str, user: dict = Depends(get_current_user)):
    app_row = _load_application(application_id)
    _assert_can_view(app_row, user)
    if app_row["status"] not in ("draft", "clarification_pending"):
        raise HTTPException(
            status_code=409,
            detail="Application cannot be submitted from status '{}'.".format(
                app_row["status"]))

    profile = db.query_one("SELECT * FROM business_profiles WHERE id=?",
                           (app_row["business_id"],))
    approval = _approval_dict(db.query_one(
        "SELECT * FROM approvals WHERE id=?", (app_row["approval_id"],)))
    documents = _app_documents(application_id)
    readiness = compute_readiness(load_profile_dict(profile), approval, documents)

    now = db._now()
    deadline = sla_deadline_for(approval["sla_days"])

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
        for off in db.query("SELECT id FROM users WHERE role='officer'"):
            notify(off["id"], "New Application Submitted",
                   "{} ({}) is awaiting assignment.".format(
                       app_row["id"], approval["name"]), application_id=app_row["id"])
        notify(profile["owner_id"], "Application Submitted",
               "Your application is in the officer queue. SLA deadline: {}".format(
                   deadline[:10]), application_id=app_row["id"])

    audit("application", app_row["id"], user, "submit",
          "Submitted. Readiness {}%. Green channel: {}".format(
              readiness["score"], "issued" if gc["issued"] else gc["reason"]),
          {"green_channel_issued": gc["issued"]})
    app_row = _load_application(app_row["id"])
    return {"application": _app_view(app_row), "readiness": readiness,
            "green_channel": gc}


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
        if not reasons:
            eligible.append({"id": scheme["id"], "name": scheme["name"],
                             "description": scheme["description"],
                             "benefits": scheme["benefits"],
                             "explanation": "All eligibility rules matched your profile."})
        else:
            others.append({"id": scheme["id"], "name": scheme["name"],
                           "eligible": False, "explanation": "; ".join(reasons)})
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


