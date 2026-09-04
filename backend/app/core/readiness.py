"""Rubric-based, explainable readiness score. NEVER framed as risk or
approval probability — only as submission completeness (doc 1.4/1.8)."""
from datetime import datetime, timedelta, timezone
from typing import Optional


def _profile_completeness(profile: dict) -> tuple:
    """(score 0..1, list of missing items)."""
    required = [
        ("name", "Business name"), ("sector", "Sector"),
        ("district", "District"), ("investment_size", "Investment size"),
        ("employee_count", "Employee count"), ("project_stage", "Project stage"),
        ("pan_hash", "PAN"), ("gst_hash", "GSTIN"),
    ]
    missing = [label for field, label in required if not profile.get(field)]
    return (len(required) - len(missing)) / len(required), missing


def compute_readiness(profile: dict, approval: dict, documents: list) -> dict:
    """Readiness = 40% doc coverage + 40% validation pass rate + 20% profile.

    Every component is returned with its reasoning (explainability NFR).
    """
    required_docs = approval.get("required_documents", [])
    docs_by_type = {}
    for doc in documents:
        docs_by_type.setdefault(doc.get("type"), []).append(doc)

    coverage_lines = []
    present = 0
    for doc_type in required_docs:
        docs = docs_by_type.get(doc_type, [])
        if docs:
            best = max(docs, key=lambda d: (d.get("checks_passed", 0), d.get("uploaded_at", "")))
            coverage_lines.append({
                "doc_type": doc_type, "present": True,
                "checks_passed": best.get("checks_passed", 0),
                "checks_total": best.get("checks_total", 0),
                "status": best.get("status", "pending"),
                "explanation": "Uploaded; {}/{} validation checks passed.".format(
                    best.get("checks_passed", 0), best.get("checks_total", 0)),
            })
            present += 1
        else:
            coverage_lines.append({
                "doc_type": doc_type, "present": False, "checks_passed": 0,
                "checks_total": 0, "status": "missing",
                "explanation": "Required document not yet uploaded.",
            })
    coverage = present / len(required_docs) if required_docs else 1.0

    total_checks = passed_checks = 0
    for doc in documents:
        total_checks += doc.get("checks_total", 0) or 0
        passed_checks += doc.get("checks_passed", 0) or 0
    validation = passed_checks / total_checks if total_checks else 0.0

    completeness, missing_fields = _profile_completeness(profile)

    score = round(100.0 * (0.4 * coverage + 0.4 * validation + 0.2 * completeness), 1)

    breakdown = [
        {"component": "Document coverage", "weight": "40%",
         "score": round(coverage * 100, 1),
         "explanation": "{}/{} required document types uploaded.".format(
             present, len(required_docs)) if required_docs
         else "No documents required for this approval.",
         "details": coverage_lines},
        {"component": "Validation pass rate", "weight": "40%",
         "score": round(validation * 100, 1),
         "explanation": "{} of {} deterministic checks passed across all documents.".format(
             passed_checks, total_checks) if total_checks
         else "No documents uploaded yet, so no checks have run."},
        {"component": "Profile completeness", "weight": "20%",
         "score": round(completeness * 100, 1),
         "explanation": ("All profile fields present." if not missing_fields
                         else "Missing: {}.".format(", ".join(missing_fields)))},
    ]

    # Attention level for the officer queue (rubric-based, not "risk").
    if score >= 85 and validation >= 0.99:
        attention = "low"
    elif score >= 60:
        attention = "medium"
    else:
        attention = "high"

    return {
        "score": score,
        "breakdown": breakdown,
        "attention_level": attention,
        "methodology": ("Rubric-based submission-completeness score. This is NOT a "
                        "risk score or approval probability — it measures how "
                        "complete and pre-validated the submission is."),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def sla_deadline_for(sla_days: int, from_dt: Optional[datetime] = None) -> str:
    base = from_dt or datetime.now(timezone.utc)
    return (base + timedelta(days=int(sla_days or 0))).isoformat()


def parse_iso(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def sla_status(application: dict) -> dict:
    deadline = parse_iso(application.get("sla_deadline"))
    if deadline is None:
        return {"state": "not_started", "remaining_hours": None, "deadline": None}
    now = datetime.now(timezone.utc)
    remaining = (deadline - now).total_seconds() / 3600.0
    if remaining <= 0:
        state = "breached"
    elif remaining <= 48:
        state = "approaching"
    else:
        state = "on_track"
    return {"state": state, "remaining_hours": round(max(remaining, 0), 1),
            "deadline": deadline.isoformat()}
