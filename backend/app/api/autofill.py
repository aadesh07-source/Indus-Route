"""DigiLocker e-KYC endpoints: consent -> OTP -> verified auto-fill.

The full Aadhaar number is transient; only masked references persist
(see core/digilocker.py for the privacy contract). Applying the verified
identity to the business profile is a separate, explicit step.

Issued-document fetch: the applicant selects required documents on the
DigiLocker consent screen; each fetched document is registered with
`ocr_source='digilocker'` and re-validated by the same deterministic
check engine used for uploads. Documents that are not DigiLocker-issued
(physical/architect-signed artefacts) fall back to manual upload.
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query

from ..models.schemas import (DigiLockerConsentRequest, DigiLockerVerifyRequest,
                              DigiLockerApplyRequest, DigiLockerFetchRequest)
from .. import db, config
from ..core import digilocker, ocr_service, pii
from ..core.digilocker import sandbox_mode
from ..core.ocr_service import run_checks, summarize_checks
from ..core.rule_engine import get_doc_spec
from ..security import sha256_hex
from .deps import get_current_user, get_own_profile, load_profile_dict, audit

router = APIRouter(tags=["digilocker"])

# Document types that exist as DigiLocker Issued Documents (digitally
# signed by the issuing authority). Physical artefacts — architect-signed
# layout plans, MIDC lease deeds — are NOT issued to DigiLocker and must
# be uploaded manually from the Upload Centre.
DIGILOCKER_ISSUED = {
    "pan_card": {"issuer": "Income Tax Department (CBDT)", "uri": "in.gov.pan-PANCR"},
    "gst_certificate": {"issuer": "GST Network (GSTN)", "uri": "in.gst-GSTREG"},
    "self_declaration": {"issuer": "Statutory e-Form (OTP-signed)", "uri": "eform-selfdec"},
}


@router.post("/digilocker/consent")
def start_consent(body: DigiLockerConsentRequest,
                  user: dict = Depends(get_current_user)):
    try:
        result = digilocker.start_consent(user, body.aadhaar_number)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    audit("kyc_consent", result["consent_id"], user, "consent_started",
          "DigiLocker consent initiated; Aadhaar stored as last-4 reference only.")
    return result


@router.post("/digilocker/consent/{consent_id}/verify")
def verify_otp(consent_id: str, body: DigiLockerVerifyRequest,
               user: dict = Depends(get_current_user)):
    try:
        return digilocker.verify_otp(user, consent_id, body.otp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/digilocker/consent/{consent_id}/apply")
def apply_verified(consent_id: str, body: DigiLockerApplyRequest,
                   user: dict = Depends(get_current_user)):
    """Merge verified identity (+ any DigiLocker-fetched PAN/GSTIN) into the
    business profile, then cross-check name/PAN against the verified bundle."""
    consent = db.query_one(
        "SELECT * FROM kyc_consents WHERE id=? AND user_id=? AND status='verified'",
        (consent_id, user["id"]))
    if consent is None:
        raise HTTPException(status_code=404,
                            detail="No verified consent found for this user.")
    profile = get_own_profile(user)

    updated = {}
    if body.authorized_person.strip():
        updated["authorized_person"] = body.authorized_person.strip()
        db.execute("UPDATE business_profiles SET authorized_person=?, updated_at=? "
                   "WHERE id=?", (body.authorized_person.strip(), db._now(),
                                  profile["id"]))
    for field, enc_col, mask_col, hash_col, value in (
            ("pan", "pan_enc", "pan_masked", "pan_hash", body.pan),
            ("gst", "gst_enc", "gst_masked", "gst_hash", body.gst)):
        if value.strip():
            db.execute(
                "UPDATE business_profiles SET {}=?, {}=?, {}=?, updated_at=? "
                "WHERE id=?".format(enc_col, mask_col, hash_col),
                (pii.encrypt_value(value.strip()),
                 pii.mask_value(value.strip()),
                 pii.reference_hash(value.strip()), db._now(), profile["id"]))
            updated[field] = pii.mask_value(value.strip())

    digilocker.mark_applied(consent_id)
    verified = db.jloads(consent["verified_data"], {})
    audit("kyc_consent", consent_id, user, "applied_to_profile",
          "Verified e-KYC data merged into the business profile.",
          {"fields": list(updated.keys()) or ["identity_only"]})
    return {
        "status": "applied",
        "verified_identity": {
            "name": verified.get("name"),
            "aadhaar_masked": "XXXX XXXX {}".format(verified.get("aadhaar_last4", "")),
            "digilocker_ref": verified.get("digilocker_ref"),
        },
        "updated_fields": updated,
        "note": ("Name/PAN/GSTIN on this profile will now be cross-checked against "
                 "uploaded documents by the deterministic validation engine."),
    }


@router.get("/digilocker/fetchable")
def fetchable_documents(application_id: str = Query(min_length=4, max_length=64),
                        user: dict = Depends(get_current_user)):
    """List an application's required documents with DigiLocker availability.

    Drives the applicant 'Documents Required' picker: fetchable types show
    the issuing authority + consent URI; physical artefacts show a manual
    upload fallback instead.
    """
    profile = get_own_profile(user)
    app_row = db.query_one("SELECT * FROM applications WHERE id=?", (application_id,))
    if app_row is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app_row["business_id"] != profile["id"]:
        raise HTTPException(status_code=403, detail="Not your application.")
    approval = db.query_one("SELECT * FROM approvals WHERE id=?",
                            (app_row["approval_id"],))
    required = db.jloads(approval.get("required_documents"), []) if approval else []
    uploaded = {r["type"]: r for r in db.query(
        "SELECT * FROM documents WHERE application_id=?", (application_id,))}
    kyc = digilocker.latest_verified(user["id"])

    docs = []
    for doc_type in required:
        spec = get_doc_spec(doc_type) or {}
        issued = DIGILOCKER_ISSUED.get(doc_type)
        up = uploaded.get(doc_type)
        docs.append({
            "type": doc_type,
            "label": spec.get("label", doc_type.replace("_", " ").title()),
            "status": ("uploaded" if up else "pending"),
            "checks_passed": up.get("checks_passed", 0) if up else 0,
            "checks_total": up.get("checks_total", 0) if up else 0,
            "digilocker_issued": bool(issued),
            "issuer": issued["issuer"] if issued else None,
            "consent_uri": issued["uri"] if issued else None,
            "manual_fallback": not bool(issued),
            "extractable_fields": list(spec.get("extractable_fields", [])),
        })
    return {
        "application_id": application_id,
        "mode": "sandbox" if sandbox_mode() else "production",
        "kyc_verified": bool(kyc),
        "docs": docs,
        "note": ("Fetchable types are DigiLocker Issued Documents — digitally signed "
                 "by the issuing authority and re-validated by the deterministic "
                 "check engine on arrival. Other types require manual upload."),
    }


@router.post("/digilocker/fetch-documents")
def fetch_documents(body: DigiLockerFetchRequest,
                    user: dict = Depends(get_current_user)):
    """Fetch the applicant-selected Issued Documents from DigiLocker.

    Production path: the consent artefact from the DigiLocker OAuth consent
    is exchanged for the signed document via the API Setu Requester API.
    Sandbox path (this demo): the applicant's registered PAN/GSTIN and
    OTP-verified identity construct the issued-document fields — then the
    SAME deterministic checks run on them exactly as for uploads.
    """
    profile = get_own_profile(user)
    app_row = db.query_one("SELECT * FROM applications WHERE id=?",
                           (body.application_id,))
    if app_row is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app_row["business_id"] != profile["id"]:
        raise HTTPException(status_code=403, detail="Not your application.")
    if app_row["status"] in ("approved", "rejected", "provisionally_cleared"):
        raise HTTPException(status_code=409,
                            detail="Documents cannot be added after a decision.")
    approval = db.query_one("SELECT * FROM approvals WHERE id=?",
                            (app_row["approval_id"],))
    required = set(db.jloads(approval.get("required_documents"), [])) if approval else set()
    kyc = digilocker.latest_verified(user["id"])
    pdict = load_profile_dict(profile)

    pan_number = pii.decrypt_value(profile.get("pan_enc") or "") or ""
    gstin = pii.decrypt_value(profile.get("gst_enc") or "") or ""
    entity_name = (kyc or {}).get("name") or profile.get("name") or ""
    kyc_ok = bool(kyc and kyc.get("kyc_status") in ("verified", "applied"))

    fetched, skipped = [], []
    for doc_type in body.doc_types:
        doc_type = doc_type.strip().lower()
        _validate_fetch_request(doc_type, required, pan_number, gstin, kyc_ok)
        already = db.query_one(
            "SELECT id FROM documents WHERE application_id=? AND type=?",
            (body.application_id, doc_type))
        if already:
            skipped.append({"type": doc_type, "reason": "already uploaded/fetched"})
            continue
        fields = _issued_fields(doc_type, profile, entity_name, pan_number, gstin)
        fetched.append(_register_fetched_doc(user, profile, body.application_id,
                                             doc_type, fields, pdict))

    have = [r["type"] for r in db.query(
        "SELECT type FROM documents WHERE application_id=?",
        (body.application_id,))]
    return {
        "status": "fetched", "fetched": fetched, "skipped": skipped,
        "mode": "sandbox" if sandbox_mode() else "production",
        "docs_registered": len(fetched),
        "still_pending": sorted(required - set(have)),
        "explainability": ("Fetched Issued Documents pass through the same deterministic "
                           "rule-table checks as manual uploads — no AI involved in "
                           "pass/fail."),
    }


def _validate_fetch_request(doc_type, required, pan_number, gstin, kyc_ok):
    """Deterministic request guards for one requested doc type."""
    if doc_type not in required:
        raise HTTPException(status_code=422,
                            detail="'{}' is not a required document for this "
                                   "application.".format(doc_type))
    if doc_type not in DIGILOCKER_ISSUED:
        raise HTTPException(status_code=422,
                            detail="'{}' is not a DigiLocker Issued Document — upload "
                                   "it manually from the Upload Centre.".format(doc_type))
    if doc_type == "pan_card" and not pan_number:
        raise HTTPException(status_code=422,
                            detail="PAN is not registered on your business profile.")
    if doc_type == "gst_certificate" and not gstin:
        raise HTTPException(status_code=422,
                            detail="GSTIN is not registered on your business profile.")
    if doc_type == "self_declaration" and not kyc_ok:
        raise HTTPException(status_code=422,
                            detail="Complete DigiLocker e-KYC OTP verification first.")


def _issued_fields(doc_type, profile, entity_name, pan_number, gstin):
    """Construct the Issued-Document field bundle (sandbox: registered + OTP data)."""
    if doc_type == "pan_card":
        return {"entity_name": entity_name, "pan_number": pan_number}
    if doc_type == "gst_certificate":
        return {"legal_name": entity_name, "gstin": gstin,
                "operating_address": ", ".join(
                    str(profile.get(f) or "") for f in
                    ("district", "industrial_zone") if profile.get(f))}
    return {"entity_name": entity_name, "pan_number": pan_number,
            "aadhaar_otp_verified": True,
            "form_hash": sha256_hex("{}|{}".format(entity_name, pan_number))}


def _register_fetched_doc(user, profile, application_id, doc_type, fields, pdict):
    """Validate + persist one fetched Issued Document (shared sandbox/production)."""
    results = run_checks(doc_type, fields, pdict)
    summary = summarize_checks(results)
    spec = get_doc_spec(doc_type) or {}
    issued = DIGILOCKER_ISSUED[doc_type]

    doc_id = db.new_id("doc")
    stub_name = re.sub(r"[^A-Za-z0-9_.-]", "_", "digilocker_{}".format(doc_type))
    safe_name = "{}_{}.txt".format(doc_id, stub_name)
    stub = json.dumps({
        "digilocker_issued": True, "doc_type": doc_type,
        "issuer": issued["issuer"], "consent_uri": issued["uri"],
        "extracted_fields": fields,
        "mode": "sandbox" if sandbox_mode() else "production",
    }, indent=2)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (config.UPLOAD_DIR / safe_name).write_text(stub, encoding="utf-8")

    reusable = 1 if summary["all_passed"] else 0
    db.execute(
        "INSERT INTO documents (id, application_id, business_id, type, label, "
        "filename, file_ref, mime, size, extracted_fields, validation_flags, "
        "checks_passed, checks_total, status, source_reusable, expiry_date, "
        "ocr_source, uploaded_at, uploaded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc_id, application_id, profile["id"], doc_type,
         spec.get("label", doc_type), safe_name, safe_name, "application/json",
         len(stub.encode("utf-8")), db.jdumps(fields), db.jdumps(results),
         summary["checks_passed"], summary["checks_total"],
         "pre_validated" if summary["all_passed"] else "needs_attention",
         reusable, None, "digilocker", db._now(), user["id"]))
    audit("document", doc_id, user, "digilocker_fetch",
          "{}/{} deterministic checks passed on the DigiLocker Issued Document "
          "({}).".format(summary["checks_passed"], summary["checks_total"],
                         issued["issuer"]),
          {"doc_type": doc_type, "issuer": issued["issuer"],
           "all_passed": summary["all_passed"]})
    return {"type": doc_type, "label": spec.get("label", doc_type),
            "issuer": issued["issuer"], "consent_uri": issued["uri"],
            "ocr_source": "digilocker", "checks": results, "summary": summary,
            "reusable": bool(reusable), "document_id": doc_id}


@router.get("/digilocker/status")
def kyc_status(user: dict = Depends(get_current_user)):
    latest = digilocker.latest_verified(user["id"])
    if not latest:
        return {"kyc_verified": False,
                "note": "No DigiLocker consent completed yet."}
    return {"kyc_verified": True, "identity": {
        "name": latest.get("name"),
        "aadhaar_masked": "XXXX XXXX {}".format(latest.get("aadhaar_last4", "")),
        "digilocker_ref": latest.get("digilocker_ref"),
        "kyc_source": latest.get("kyc_source"),
        "verified_at": latest.get("verified_at"),
        "status": latest.get("kyc_status"),
    }}
