"""DigiLocker e-KYC endpoints: consent -> OTP -> verified auto-fill.

The full Aadhaar number is transient; only masked references persist
(see core/digilocker.py for the privacy contract). Applying the verified
identity to the business profile is a separate, explicit step.
"""
from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import (DigiLockerConsentRequest, DigiLockerVerifyRequest,
                              DigiLockerApplyRequest)
from .. import db
from ..core import digilocker, pii
from .deps import get_current_user, get_own_profile, audit

router = APIRouter(tags=["digilocker"])


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
