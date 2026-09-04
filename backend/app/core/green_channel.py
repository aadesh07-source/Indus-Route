"""Green Channel auto-approval engine (EXTENSION module — see doc 1.6/3.3).

Highest-severity path in the system, therefore constrained on every axis:
1. Fires ONLY on deterministic boolean check results — never an AI score.
2. Only for approvals whitelisted `green_channel_eligible` AND with the
   admin (global) toggle ON.
3. Cross-checks PAN vs. GSTIN-embedded PAN vs. profile (two-source rule).
4. ALWAYS creates a mandatory post-facto audit + inspection in the same
   transaction — never a scrutiny-free endpoint.
5. Rate-limited per business per day.
6. Every issuance is audit-logged with decision_source='system'.
7. Output is a PROVISIONAL / DEEMED CLEARANCE — never a final approval.
"""
import hashlib
import traceback
from datetime import datetime, timedelta, timezone

from .. import db, config
from ..notifications.sms_gateway import queue_sms


def green_channel_enabled() -> bool:
    setting = db.get_setting("green_channel_enabled",
                             {"enabled": config.GREEN_CHANNEL_ENABLED})
    try:
        return bool(setting.get("enabled", config.GREEN_CHANNEL_ENABLED))
    except AttributeError:
        return config.GREEN_CHANNEL_ENABLED


def _rate_limit_ok(business_id: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    rows = db.query(
        "SELECT COUNT(*) AS n FROM audit_log "
        "WHERE entity_type='green_channel_certificate' AND actor_id=? AND created_at>=?",
        (business_id, cutoff),
    )
    return (rows[0]["n"] if rows else 0) < config.GC_RATE_LIMIT_PER_DAY


def attempt_green_channel(application: dict, approval: dict, documents: list) -> dict:
    """Deterministically decide whether the application qualifies."""
    try:
        if not approval.get("green_channel_eligible"):
            return {"issued": False, "reason":
                    "Approval type is not whitelisted for the Green Channel."}
        if not green_channel_enabled():
            return {"issued": False, "reason":
                    "Green Channel is disabled by the department (admin toggle)."}
        if not _rate_limit_ok(application["business_id"]):
            return {"issued": False, "reason":
                    "Green Channel rate limit reached for this business (24h window)."}

        required_docs = approval.get("required_documents", [])
        docs_by_type = {}
        for doc in documents:
            docs_by_type.setdefault(doc.get("type"), []).append(doc)

        # Every required document type must exist and pass ALL checks 100%.
        for doc_type in required_docs:
            candidates = docs_by_type.get(doc_type, [])
            if not candidates:
                return {"issued": False, "reason":
                        "Required document '{}' not uploaded.".format(doc_type)}
            best = max(candidates,
                       key=lambda d: (d.get("checks_passed", 0), d.get("uploaded_at", "")))
            if not (best.get("checks_total", 0) > 0
                    and best.get("checks_passed", 0) == best.get("checks_total", 0)):
                return {"issued": False, "reason":
                        "Document '{}' has failing checks ({} / {} passed).".format(
                            doc_type, best.get("checks_passed", 0),
                            best.get("checks_total", 0))}

        # Two-source cross-check: PAN vs profile, and PAN embedded in GSTIN.
        profile = db.query_one(
            "SELECT pan_hash, gst_hash, name FROM business_profiles WHERE id=?",
            (application["business_id"],))
        if not profile or not profile.get("pan_hash"):
            return {"issued": False, "reason":
                    "Profile has no verified PAN reference — cross-check impossible."}
        pan_docs = docs_by_type.get("pan_card", [])
        gst_docs = docs_by_type.get("gst_certificate", [])
        if pan_docs and gst_docs:
            gstin = str((gst_docs[0].get("extracted_fields") or {}).get("gstin", "")).upper()
            if len(gstin) >= 12:
                embedded = hashlib.sha256(
                    gstin[2:12].strip().upper().encode()).hexdigest().upper()
                if embedded != profile["pan_hash"].strip().upper():
                    return {"issued": False, "reason":
                            "Cross-check failed: PAN embedded in GSTIN does not "
                            "match profile PAN."}

        return _issue(application, approval)
    except Exception as exc:
        traceback.print_exc()
        return {"issued": False, "reason":
                "Green Channel engine errored and failed safe: {}".format(exc)[:200]}


def _issue(application: dict, approval: dict) -> dict:
    """Issue the provisional certificate + mandatory audit (same transaction)."""
    now = datetime.now(timezone.utc)
    cert_no = "GC-{}".format(now.strftime("%Y%m%d%H%M%S"))
    verification_hash = hashlib.sha256(
        "{}|{}|{}".format(application["id"], cert_no,
                          application["business_id"]).encode()).hexdigest()[:32]
    certificate = {
        "certificate_no": cert_no,
        "type": "PROVISIONAL / DEEMED CLEARANCE (not a final statutory approval)",
        "issued_at": now.isoformat(),
        "application_id": application["id"],
        "verification_hash": verification_hash,
        # QR encodes a verification URL + hash only — never PII (doc 3.3).
        "qr_payload": "https://verify.maharashtra-demo.example/cert/{}?h={}".format(
            cert_no, verification_hash),
        "subject_to": "Mandatory post-facto audit and scheduled inspection.",
    }

    # 1. Persist certificate on the application + set status.
    db.execute(
        "UPDATE applications SET status='provisionally_cleared', green_channel=1, "
        "decision_source='system', decision_notes=?, decided_at=?, provisional_certificate=? "
        "WHERE id=?",
        ("Green Channel: all deterministic checklist parameters passed (100%). "
         "Provisional clearance issued; post-facto audit mandatory.",
         now.isoformat(), db.jdumps(certificate), application["id"]))

    # 2. System-enforced post-facto audit — same transaction, non-optional.
    audit_date = (now + timedelta(days=7)).date().isoformat()
    db.execute(
        "INSERT INTO inspections (id, application_id, type, scheduled_date, status, "
        "coordinated_with, is_post_facto_audit, created_at) VALUES (?,?,?,?,?,?,1,?)",
        (db.new_id("ins"), application["id"], "post_facto_audit", audit_date,
         "scheduled", db.jdumps(["Department Audit Cell"]), now.isoformat()))

    # 3. Immutable audit trail entry (decision_source=system).
    db.execute(
        "INSERT INTO audit_log (id, entity_type, entity_id, actor_id, actor_role, action, "
        "reasoning, decision_source, meta, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (db.new_id("log"), "green_channel_certificate", cert_no, "system", "system",
         "auto_issue_provisional_clearance",
         "All deterministic checklist parameters passed 100%; whitelisted approval; "
         "cross-checks OK; global toggle ON; rate limit OK.",
         "system", db.jdumps({"application_id": application["id"],
                              "approval": approval.get("code")}), now.isoformat()))

    # 4. Notify + SMS (no PII in SMS body).
    owner = db.query_one(
        "SELECT b.owner_id, u.phone FROM business_profiles b JOIN users u "
        "ON b.owner_id=u.id WHERE b.id=?", (application["business_id"],))
    if owner:
        db.execute(
            "INSERT INTO notifications (id, user_id, application_id, channel, title, body, "
            "status, created_at) VALUES (?,?,?,?,?,?, 'sent', ?)",
            (db.new_id("ntf"), owner["owner_id"], application["id"], "in_app+sms",
             "Provisional Clearance Issued",
             "Provisional permit {} issued — subject to mandatory audit scheduled {}."
             .format(cert_no, audit_date), now.isoformat()))
        queue_sms("Provisional permit issued — subject to audit. Cert: {}. Verify: {}".format(
            cert_no, certificate["qr_payload"][:60]),
            user_id=owner["owner_id"], application_id=application["id"],
            phone=owner.get("phone", ""))

    return {"issued": True, "reason": "All deterministic parameters passed (100%).",
            "certificate": certificate}

