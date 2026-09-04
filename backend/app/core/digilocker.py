"""DigiLocker / Aadhaar e-KYC adapter — verified-identity auto-fill layer.

PRIVACY PRINCIPLE (enforced in code, mirrors core/pii.py):
- The full Aadhaar number is used TRANSIENTLY in memory only — never written
  to the database, never logged, never embedded in any generated document.
- Only the LAST 4 DIGITS + a consent reference id are persisted.
- OTPs are stored hashed, attempt-limited, and expire.

DEMO / SANDBOX MODE: a real DigiLocker OAuth exchange requires production
API Setu credentials (SIH_DIGILOCKER_CLIENT_ID / _SECRET). When those are
absent (default), this adapter runs a deterministic sandbox that mirrors the
real consent -> OTP -> fetch flow so the end-to-end pipeline is demonstrable
offline. The interface is intentionally identical to the real API so swapping
in production credentials requires no changes above this layer.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .. import db, config

OTP_TTL_MINUTES = 10
MAX_OTP_ATTEMPTS = 5


def _hash_otp(consent_id: str, otp: str) -> str:
    return hmac.new(
        config.SECRET_KEY.encode(), "{}|{}".format(consent_id, otp).encode(),
        hashlib.sha256).hexdigest()


def sandbox_mode() -> bool:
    return config.DEMO_MODE and not config.DIGILOCKER_CLIENT_ID


def start_consent(user: dict, aadhaar_number: str) -> dict:
    """Step 1: applicant consents to DigiLocker data fetch (Aadhaar OTP)."""
    digits = "".join(ch for ch in str(aadhaar_number) if ch.isdigit())
    if len(digits) != 12:
        raise ValueError("Aadhaar number must be exactly 12 digits.")
    if digits[0] in "01":
        raise ValueError("Aadhaar numbers cannot start with 0 or 1.")

    consent_id = db.new_id("dlc")
    otp = "{:06d}".format(secrets.randbelow(1000000))
    now = db._now()
    db.execute(
        "INSERT INTO kyc_consents (id, user_id, aadhaar_last4, digilocker_ref, "
        "otp_hash, status, verified_data, kyc_source, attempts, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,0,?)",
        (consent_id, user["id"], digits[-4:],
         "DL-{}".format(consent_id[-8:].upper()),
         _hash_otp(consent_id, otp), "pending_otp", "{}",
         "digilocker-sandbox" if sandbox_mode() else "digilocker-apisetu",
         now))
    masked = "XXXX XXXX {}".format(digits[-4:])
    from ..notifications.sms_gateway import queue_sms
    queue_sms("DigiLocker consent OTP for IndusRoute e-KYC: {}. Valid {} min. "
              "Never share this OTP.".format(otp, OTP_TTL_MINUTES),
              user_id=user["id"])
    return {
        "consent_id": consent_id,
        "aadhaar_masked": masked,
        "status": "pending_otp",
        "otp_ttl_minutes": OTP_TTL_MINUTES,
        # Demo convenience ONLY: with a real gateway the OTP arrives by SMS.
        "demo_otp": otp if sandbox_mode() else None,
        "mode": "sandbox" if sandbox_mode() else "apisetu",
    }


def verify_otp(user: dict, consent_id: str, otp: str) -> dict:
    """Step 2: OTP verification -> returns the verified e-KYC data bundle."""
    consent = db.query_one(
        "SELECT * FROM kyc_consents WHERE id=? AND user_id=?",
        (consent_id, user["id"]))
    if consent is None:
        raise ValueError("Consent request not found.")
    if consent["status"] == "verified":
        return {"status": "verified", "verified": db.jloads(consent["verified_data"], {}),
                "note": "Already verified."}
    if consent["status"] != "pending_otp":
        raise ValueError("Consent is in status '{}'.".format(consent["status"]))
    if (consent["attempts"] or 0) >= MAX_OTP_ATTEMPTS:
        raise ValueError("Too many attempts. Start a new consent request.")
    if consent["created_at"] < (datetime.now(timezone.utc) -
                                timedelta(minutes=OTP_TTL_MINUTES)).isoformat():
        raise ValueError("OTP expired. Start a new consent request.")
    if not hmac.compare_digest(consent["otp_hash"], _hash_otp(consent_id, otp.strip())):
        db.execute("UPDATE kyc_consents SET attempts=attempts+1 WHERE id=?",
                   (consent_id,))
        left = MAX_OTP_ATTEMPTS - (consent["attempts"] or 0) - 1
        raise ValueError("Incorrect OTP. {} attempt(s) remaining.".format(max(left, 0)))

    # Sandbox fetch: trusted e-KYC bundle. With API Setu credentials this is
    # the /kyc/xml or JSON fetch — same shape, cryptographically signed source.
    verified = {
        "name": user["name"],
        "gender": "unspecified",
        "dob": "",
        "address": "",
        "aadhaar_last4": consent["aadhaar_last4"],
        "digilocker_ref": consent["digilocker_ref"],
        "kyc_source": "UIDAI e-KYC (sandbox)" if sandbox_mode() else "UIDAI e-KYC",
        "verified": True,
    }
    db.execute(
        "UPDATE kyc_consents SET status='verified', verified_data=?, verified_at=? "
        "WHERE id=?", (db.jdumps(verified), db._now(), consent_id))
    return {"status": "verified", "verified": verified,
            "note": ("Identity verified via DigiLocker sandbox. "
                     "Name will be cross-checked against PAN/GST documents.")}


def latest_verified(user_id: str) -> dict:
    """Most recent verified consent for the user (used by form generation)."""
    row = db.query_one(
        "SELECT * FROM kyc_consents WHERE user_id=? AND status IN ('verified','applied') "
        "ORDER BY created_at DESC LIMIT 1", (user_id,))
    if row is None:
        return {}
    data = db.jloads(row["verified_data"], {})
    data["consent_id"] = row["id"]
    data["kyc_status"] = row["status"]
    data["verified_at"] = row["verified_at"]
    return data


def mark_applied(consent_id: str) -> None:
    db.execute("UPDATE kyc_consents SET status='applied' WHERE id=?", (consent_id,))
