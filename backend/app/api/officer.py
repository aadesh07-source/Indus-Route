"""Officer endpoints: queue, AI pre-scrutiny summary, decisions,
AI-drafted clarifications (edit-before-send), inspection scheduling."""
from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import DecisionRequest, InspectionRequest
from .. import db, config
from ..core.ai_service import draft_clarification, pre_scrutiny_summary
from ..core.readiness import sla_status
from ..core import green_channel
from .deps import require_roles, audit, notify

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
    return {
        "application": dict(app_row),
        "approval_name": approval["name"] if approval else "",
        "approval_code": approval["code"] if approval else "",
        "business_name": profile["name"] if profile else "",
        "readiness_score": app_row["readiness_score"],
        "documents": _app_docs(app_row["id"]),
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
    return {
        "ai_summary": summary,          # AI suggestion (checklist, not verdict)
        "deterministic_data": {         # system facts
            "readiness_score": app_row["readiness_score"],
            "decision_source": app_row["decision_source"],
            "documents": ctx["documents"],
            "green_channel_eligible": bool(app_row["green_channel"]),
        },
        "principle": "AI explains; rules and the officer decide.",
    }


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

    # Approve / Reject — ALWAYS officer-initiated (FR-18).
    if body.action == "approve":
        open_req = db.query_one(
            "SELECT id FROM clarification_requests WHERE application_id=? "
            "AND status='open'", (application_id,))
        if open_req:
            raise HTTPException(
                status_code=409,
                detail="An open clarification request must be resolved first.")
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
    if profile:
        notify(profile["owner_id"],
               "Application {}".format(new_status.replace("_", " ").title()),
               body.notes or "Decision recorded.", application_id=application_id,
               sms_body="Application {} status: {}.".format(
                   application_id[-8:], new_status.replace("_", " ")))
    return {"status": new_status, "decision_source": "human"}


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


