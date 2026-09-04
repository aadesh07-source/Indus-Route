"""Admin endpoints: KPIs, deficiency/bottleneck analytics, grievances,
scheme utilization, green-channel toggle, audit trail."""
from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import GreenChannelToggleRequest
from .. import db
from ..core import green_channel
from .deps import require_roles, audit

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/analytics/summary")
def analytics_summary(user: dict = Depends(require_roles("admin"))):
    total = db.query_one("SELECT COUNT(*) AS n FROM applications")["n"]
    by_status = {r["status"]: r["n"] for r in db.query(
        "SELECT status, COUNT(*) AS n FROM applications GROUP BY status")}
    sla_breached = db.query_one(
        "SELECT COUNT(*) AS n FROM applications WHERE sla_deadline IS NOT NULL "
        "AND sla_deadline < ? AND status NOT IN ('approved','rejected','provisionally_cleared')",
        (db._now(),))["n"]

    # Deficiency analytics: most common failing checks.
    deficiency = {}
    docs = db.query("SELECT validation_flags FROM documents")
    for doc in docs:
        for flag in db.jloads(doc["validation_flags"], []):
            if not flag.get("passed", False):
                key = flag.get("check_id", "unknown")
                deficiency[key] = deficiency.get(key, 0) + 1
    deficiency_top = sorted(
        [{"check": k, "count": v} for k, v in deficiency.items()],
        key=lambda x: -x["count"])[:10]

    # Bottleneck analytics: avg processing time per approval type.
    bottleneck = db.query(
        "SELECT ap.code, ap.name, ap.department, COUNT(a.id) AS applications, "
        "AVG(ap.sla_days) AS avg_sla_days FROM approvals ap "
        "LEFT JOIN applications a ON a.approval_id=ap.id "
        "GROUP BY ap.id ORDER BY applications DESC")

    grievance_stats = {r["status"]: r["n"] for r in db.query(
        "SELECT status, COUNT(*) AS n FROM grievances GROUP BY status")}
    grievance_open = db.query(
        "SELECT id, reason, status, escalation_level, created_at FROM grievances "
        "WHERE status='open' ORDER BY created_at LIMIT 50")

    green_channel_count = db.query_one(
        "SELECT COUNT(*) AS n FROM applications WHERE green_channel=1")["n"]
    reusable_docs = db.query_one(
        "SELECT COUNT(*) AS n FROM documents WHERE source_reusable=1")["n"]
    total_docs = db.query_one("SELECT COUNT(*) AS n FROM documents")["n"]

    return {
        "kpis": {
            "total_applications": total,
            "by_status": by_status,
            "sla_breached_active": sla_breached,
            "green_channel_certificates": green_channel_count,
            "reusable_documents": reusable_docs,
            "total_documents": total_docs,
        },
        "deficiency_analytics": deficiency_top,
        "bottleneck_analytics": bottleneck,
        "grievance_monitoring": {"by_status": grievance_stats, "open": grievance_open},
        "scheme_utilization": {"note": "Mock aggregate — matched schemes vs claimed.",
                               "eligible_surface_rate": "per-applicant via /schemes/recommendations"},
    }


@router.get("/green-channel/status")
def gc_status(user: dict = Depends(require_roles("admin"))):
    return {"enabled": green_channel.green_channel_enabled(),
            "default_from_env": green_channel.green_channel_enabled(),
            "note": "Toggle is global; per-approval whitelisting comes from the rule table."}


@router.post("/green-channel/toggle")
def gc_toggle(body: GreenChannelToggleRequest,
              user: dict = Depends(require_roles("admin"))):
    db.set_setting("green_channel_enabled", {"enabled": body.enabled})
    audit("setting", "green_channel_enabled", user,
          "enable_green_channel" if body.enabled else "disable_green_channel",
          "Global Green Channel toggle changed by admin.")
    return {"enabled": body.enabled}


@router.get("/audit-log")
def audit_log(limit: int = 200, user: dict = Depends(require_roles("admin"))):
    limit = max(1, min(limit, 1000))
    rows = db.query("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,))
    return {"audit_log": rows,
            "integrity": "append-only (DB triggers block UPDATE/DELETE)"}


@router.get("/users")
def list_users(user: dict = Depends(require_roles("admin"))):
    rows = db.query("SELECT id, name, phone, email, role, created_at FROM users")
    return {"users": rows}
