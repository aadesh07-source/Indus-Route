"""Business profile endpoints + personalized rule-engine checklist."""
from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import ProfileRequest
from .. import db
from ..core import pii
from ..core.rule_engine import evaluate_profile, list_sectors
from ..core.ai_service import summarize_rule_output
from .deps import get_current_user, get_own_profile, load_profile_dict, audit

router = APIRouter(tags=["profiles"])


@router.get("/sectors")
def sectors():
    return {"sectors": list_sectors()}


@router.post("/profiles")
def create_or_update_profile(body: ProfileRequest,
                             user: dict = Depends(get_current_user)):
    if user["role"] not in ("applicant", "consultant"):
        raise HTTPException(status_code=403,
                            detail="Only applicant/consultant accounts manage business profiles.")
    if body.sector.strip().lower() not in {s["sector"] for s in list_sectors()}:
        raise HTTPException(
            status_code=422,
            detail="Unknown sector '{}'. Available: {}".format(
                body.sector, ", ".join(s["sector"] for s in list_sectors())))

    pan_hash = pii.reference_hash(body.pan) if body.pan else ""
    gst_hash = pii.reference_hash(body.gst) if body.gst else ""
    values = (
        body.name.strip(), body.sector.strip().lower(), body.district.strip(),
        body.industrial_zone.strip(), body.investment_size, body.employee_count,
        body.project_stage, body.authorized_person.strip(),
        pii.encrypt_value(body.pan), pii.mask_value(body.pan) if body.pan else "",
        pan_hash,
        pii.encrypt_value(body.gst), pii.mask_value(body.gst) if body.gst else "",
        gst_hash, body.registration_no.strip(),
    )
    existing = db.query_one("SELECT id FROM business_profiles WHERE owner_id=?",
                            (user["id"],))
    now = db._now()
    if existing:
        db.execute(
            "UPDATE business_profiles SET name=?, sector=?, district=?, industrial_zone=?, "
            "investment_size=?, employee_count=?, project_stage=?, authorized_person=?, "
            "pan_enc=?, pan_masked=?, pan_hash=?, gst_enc=?, gst_masked=?, gst_hash=?, "
            "registration_no=?, updated_at=? WHERE id=?",
            values + (now, existing["id"]),
        )
        profile_id = existing["id"]
        action = "update_profile"
    else:
        profile_id = db.new_id("biz")
        db.execute(
            "INSERT INTO business_profiles (id, owner_id, name, sector, district, "
            "industrial_zone, investment_size, employee_count, project_stage, "
            "authorized_person, pan_enc, pan_masked, pan_hash, gst_enc, gst_masked, "
            "gst_hash, registration_no, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (profile_id, user["id"]) + values + (now, now),
        )
        action = "create_profile"
    audit("business_profile", profile_id, user, action,
          "Profile saved; PAN/GST stored encrypted+hashed, masked on display.")
    return {"profile_id": profile_id, "updated": bool(existing),
            "pii": pii.pii_status()}


@router.get("/profiles/me")
def my_profile(user: dict = Depends(get_current_user)):
    profile = get_own_profile(user)
    checklist = evaluate_profile(load_profile_dict(profile))
    return {"profile": _public_profile(profile), "checklist": checklist,
            "ai_summary": summarize_rule_output(checklist)}


@router.get("/rule-engine/checklist")
def checklist(user: dict = Depends(get_current_user)):
    profile = get_own_profile(user)
    return evaluate_profile(load_profile_dict(profile))


@router.post("/rule-engine/evaluate")
def evaluate_raw(body: dict):
    """Pure preview: evaluate an ad-hoc profile dict (no persistence).

    Useful for demos/judges to prove determinism — same input always
    produces the same output, and no AI is involved.
    """
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Expected a JSON object profile.")
    return {"result": evaluate_profile(body), "deterministic": True, "ai_used": False}


@router.get("/profiles/me/pii/pan")
def reveal_pan(user: dict = Depends(get_current_user)):
    """Owner-only full-value view (officers see masked values)."""
    profile = get_own_profile(user)
    value = pii.decrypt_value(profile.get("pan_enc", "")) or profile.get("pan_masked", "")
    audit("business_profile", profile["id"], user, "reveal_pan",
          "Owner requested full PAN view.")
    return {"pan": value}


def _public_profile(profile: dict) -> dict:
    return {
        "id": profile["id"], "name": profile["name"], "sector": profile["sector"],
        "district": profile["district"], "industrial_zone": profile["industrial_zone"],
        "investment_size": profile["investment_size"],
        "employee_count": profile["employee_count"],
        "project_stage": profile["project_stage"],
        "authorized_person": profile["authorized_person"],
        "pan_masked": profile["pan_masked"], "gst_masked": profile["gst_masked"],
        "registration_no": profile["registration_no"],
    }
