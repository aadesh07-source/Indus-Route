"""Document pipeline: file validation, OCR extraction, deterministic checks.

- File type/size are verified via magic bytes (client Content-Type is never
  trusted) before anything is persisted.
- EasyOCR is used when installed; otherwise a demo extractor (plain-text
  key/value parsing or client-declared fields, flagged `demo`) is used.
- Extracted text is treated as UNTRUSTED data: it only ever flows through
  the deterministic check validators below, never into prompts/SQL/shells.
"""
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException

from .. import config
from . import rule_engine
from ..security import sha256_hex

_MAGIC_SIGNATURES = {
    b"%PDF": "application/pdf",
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}
_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}
_TEXT_EXTENSION = ".txt"


def validate_file(filename: str, content: bytes) -> str:
    """Validate size/extension/magic bytes. Raises HTTPException on violation.

    Returns the resolved MIME type.
    """
    max_bytes = max(1, config.MAX_UPLOAD_MB) * 1024 * 1024
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the {} MB upload limit.".format(config.MAX_UPLOAD_MB),
        )
    safe_name = (filename or "upload").replace("\\", "/").split("/")[-1]
    ext = ("." + safe_name.rsplit(".", 1)[-1].lower()) if "." in safe_name else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type '{}'. Allowed: {}".format(
                ext or "(none)", ", ".join(sorted(_ALLOWED_EXTENSIONS))
            ),
        )
    mime = None
    for signature, detected in _MAGIC_SIGNATURES.items():
        if content.startswith(signature):
            mime = detected
            break
    if mime is None:
        if ext == _TEXT_EXTENSION:
            mime = "text/plain"
        else:
            # Magic bytes don't match the claimed document type — reject
            # (protects the OCR pipeline from spoofed/malicious payloads).
            raise HTTPException(
                status_code=415,
                detail="File content does not match its extension (magic-byte check failed).",
            )
    return mime


def _extract_from_text(content: bytes) -> dict:
    """Parse 'key: value' lines from a plain-text document (demo extractor)."""
    fields: dict = {}
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return fields
    for line in text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = re.sub(r"[^a-z0-9_]", "_", key.strip().lower()).strip("_")
            value = value.strip()
            if key and value:
                fields[key] = value
    return fields


def _run_easyocr(content: bytes, mime: str) -> Optional[dict]:
    """Attempt real OCR via EasyOCR. Returns parsed fields or None."""
    try:
        import easyocr  # type: ignore
        import numpy as np  # type: ignore
        from PIL import Image  # type: ignore
        import io
    except ImportError:
        return None
    try:
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        if mime == "application/pdf":
            return None  # PDF rasterisation is out of scope for the demo
        image = Image.open(io.BytesIO(content))
        array = np.array(image)
        lines = reader.readtext(array, detail=0)
        return _extract_from_text("\n".join(lines).encode("utf-8"))
    except Exception:
        return None


def extract_fields(
    filename: str,
    content: bytes,
    mime: str,
    client_fields: Optional[dict] = None,
) -> tuple:
    """Extract fields from the document.

    Returns (fields: dict, ocr_source: str). In demo mode, client-declared
    fields are accepted when no OCR engine is available; this is flagged so
    the UI can distinguish declared vs. machine-extracted data.
    """
    if mime == "text/plain" or filename.lower().endswith(_TEXT_EXTENSION):
        fields = _extract_from_text(content)
        if fields:
            return fields, "text-parse"
    ocr_fields = _run_easyocr(content, mime)
    if ocr_fields:
        return ocr_fields, "easyocr"
    if config.DEMO_MODE and client_fields:
        sanitized = {}
        for key, value in dict(client_fields).items():
            safe_key = re.sub(r"[^a-z0-9_]", "_", str(key).strip().lower())[:60]
            if safe_key and isinstance(value, (str, int, float, bool)):
                sanitized[safe_key] = str(value) if not isinstance(value, bool) else value
        return sanitized, "client-declared (demo mode)"
    return {}, "none"


# --------------------------------------------------------------- check engine
def _name_similarity(a: str, b: str) -> float:
    """Token-overlap similarity between two names (0..1)."""
    stop = {"pvt", "ltd", "limited", "private", "the", "and", "industries", "enterprises"}
    ta = {t for t in re.split(r"\W+", (a or "").lower()) if t and t not in stop}
    tb = {t for t in re.split(r"\W+", (b or "").lower()) if t and t not in stop}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _eval_check(check: dict, fields: dict, profile: dict) -> dict:
    """Evaluate one deterministic check. Every branch returns a full result."""
    check_id = check.get("id", "unknown")
    param = check.get("param", "")
    raw_value = fields.get(param, "")
    value = str(raw_value).strip() if not isinstance(raw_value, bool) else raw_value
    ctype = check.get("type", "")
    description = check.get("description", "")

    passed, reason = False, ""
    try:
        if ctype == "regex":
            passed = bool(re.fullmatch(check.get("pattern", ""), str(value)))
            reason = "Format matched." if passed else "Value '{}' does not match the required format.".format(value or "(missing)")
        elif ctype == "prefix":
            passed = str(value).startswith(str(check.get("value", "")))
            reason = "Prefix matched." if passed else "Value must start with '{}'.".format(check.get("value"))
        elif ctype == "presence":
            passed = bool(value)
            reason = "Present." if passed else "'{}' is missing from the document.".format(param)
        elif ctype == "equals":
            expected = check.get("value")
            if isinstance(expected, bool):
                passed = value is expected or str(value).lower() == str(expected).lower()
            else:
                passed = str(value) == str(expected)
            reason = "Matched." if passed else "Expected '{}'.".format(expected)
        elif ctype == "field_hash_equals_profile":
            profile_hash = (profile.get(check.get("profile_field", "")) or "").strip().lower()
            if not value:
                passed, reason = False, "'{}' is missing from the document.".format(param)
            elif not profile_hash:
                passed, reason = False, "Business profile has no registered value to compare against."
            else:
                passed = sha256_hex(str(value)) == profile_hash
                reason = ("Matches the registered profile value."
                          if passed else
                          "Does not match the value registered in the business profile.")
        elif ctype == "gstin_pan_link":
            gstin = str(value).strip().upper()
            profile_hash = (profile.get(check.get("profile_field", "")) or "").strip().lower()
            if len(gstin) < 12:
                passed, reason = False, "GSTIN too short to contain an embedded PAN."
            elif not profile_hash:
                passed, reason = False, "Business profile has no registered PAN to compare."
            else:
                passed = sha256_hex(gstin[2:12]) == profile_hash
                reason = ("Embedded PAN matches the registered PAN."
                          if passed else
                          "PAN embedded in GSTIN does not match the registered PAN.")
        else:
            passed, reason = _eval_check_extended(check, fields, profile, value, ctype)
    except Exception as exc:  # never let a bad field crash the pipeline
        passed, reason = False, "Check errored and failed safe: {}".format(exc)

    return {"check_id": check_id, "param": param, "type": ctype,
            "description": description, "passed": passed, "reason": reason}


def _eval_check_extended(check, fields, profile, value, ctype):
    """Remaining check types (name/date/integrity)."""
    if ctype == "name_similarity":
        threshold = float(check.get("threshold", 0.75))
        score = _name_similarity(str(value), str(profile.get(check.get("profile_field", "name"), "")))
        return score >= threshold, "Name consistency score {:.0%} (threshold {:.0%}).".format(score, threshold)
    if ctype == "date_after":
        doc_date = _parse_date(value)
        min_days = int(check.get("min_days", 0))
        cutoff = date.today() + timedelta(days=min_days)
        if doc_date is None:
            return False, "No valid expiry date found (expected YYYY-MM-DD or DD-MM-YYYY)."
        if doc_date >= cutoff:
            return True, "Valid until {} (required: on or after {}).".format(doc_date.isoformat(), cutoff.isoformat())
        return False, "Expiry {} is before the minimum validity date {}.".format(doc_date.isoformat(), cutoff.isoformat())
    if ctype == "declaration_integrity":
        otp_ok = fields.get("aadhaar_otp_verified")
        otp_ok = otp_ok is True or str(otp_ok).strip().lower() in ("true", "yes", "1")
        if not otp_ok:
            return False, "Aadhaar OTP verification not marked as complete."
        expected_hash = sha256_hex("{}|{}".format(
            fields.get("entity_name", ""), fields.get("pan_number", "")))
        provided = str(value).strip().lower()
        if not provided:
            return False, "form_hash missing from the declaration."
        if provided == expected_hash:
            return True, "Cryptographic hash matches the statutory form fields."
        return False, "form_hash does not match the statutory fields."
    return False, "Unknown check type '{}' — failing safe.".format(ctype)


def run_checks(doc_type: str, fields: dict, profile: dict) -> list:
    """Run every deterministic check defined for a document type."""
    spec = rule_engine.get_doc_spec(doc_type)
    if spec is None:
        return [{"check_id": "doc_type_unknown", "param": "", "type": "unknown",
                 "description": "No rule-table entry for document type '{}'.".format(doc_type),
                 "passed": False,
                 "reason": "Unknown document type — failing safe."}]
    results = []
    for check in spec.get("checks", []):
        results.append(_eval_check(check, fields or {}, profile or {}))
    return results


def summarize_checks(results: list) -> dict:
    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    return {
        "checks_passed": passed,
        "checks_total": total,
        "all_passed": total > 0 and passed == total,
    }


