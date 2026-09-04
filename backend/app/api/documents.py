"""Document endpoints: upload -> file validation -> extraction -> pre-validation.

Security posture (doc 3.2): magic-byte + size checks before persistence,
extracted text treated as untrusted data, private file store with
owner/officer-only retrieval (signed-URL analogue for the demo).
"""
import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from .. import db, config
from ..core import ocr_service
from ..core import rule_engine
from ..core.rule_engine import get_doc_spec
from .deps import get_current_user, get_own_profile, load_profile_dict, audit

router = APIRouter(tags=["documents"])


@router.post("/documents/upload")
async def upload_document(
    application_id: str = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    extracted_fields_json: str = Form(default=""),
    user: dict = Depends(get_current_user),
):
    profile = get_own_profile(user)

    app_row = db.query_one("SELECT * FROM applications WHERE id=?", (application_id,))
    if app_row is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app_row["business_id"] != profile["id"]:
        raise HTTPException(status_code=403, detail="Not your application.")
    if app_row["status"] in ("approved", "rejected", "provisionally_cleared"):
        raise HTTPException(
            status_code=409,
            detail="Documents cannot be added after a decision (status '{}').".format(
                app_row["status"]))

    # 1. File validation (magic bytes, size, extension) — never trust the client.
    content = await file.read()
    try:
        mime = ocr_service.validate_file(file.filename or "upload", content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400,
                            detail="File validation error: {}".format(exc))

    # 2. Extraction (OCR / text-parse / client-declared demo fields).
    client_fields = None
    if extracted_fields_json:
        try:
            client_fields = json.loads(extracted_fields_json)
            if not isinstance(client_fields, dict):
                client_fields = None
        except ValueError:
            client_fields = None
    fields, ocr_source = ocr_service.extract_fields(
        file.filename or "upload", content, mime, client_fields)

    # 3. Deterministic checklist evaluation (rules decide, never the AI).
    doc_type = doc_type.strip().lower()
    results = ocr_service.run_checks(doc_type, fields, load_profile_dict(profile))
    summary = ocr_service.summarize_checks(results)
    spec = get_doc_spec(doc_type)
    expiry = str(fields.get("expiry_date", ""))[:10] if fields.get("expiry_date") else None

    # 4. Persist to private store.
    doc_id = db.new_id("doc")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(file.filename or "upload"))
    stored_name = "{}_{}".format(doc_id, safe_name)
    stored_path = config.UPLOAD_DIR / stored_name
    try:
        with open(stored_path, "wb") as fh:
            fh.write(content)
    except OSError as exc:
        raise HTTPException(status_code=500,
                            detail="Could not store the file: {}".format(exc))

    reusable = 1 if summary["all_passed"] else 0  # verified data reuse layer
    db.execute(
        "INSERT INTO documents (id, application_id, business_id, type, label, filename, "
        "file_ref, mime, size, extracted_fields, validation_flags, checks_passed, "
        "checks_total, status, source_reusable, expiry_date, ocr_source, uploaded_at, "
        "uploaded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc_id, application_id, profile["id"], doc_type,
         spec["label"] if spec else doc_type, safe_name, stored_name, mime, len(content),
         db.jdumps(fields), db.jdumps(results), summary["checks_passed"],
         summary["checks_total"],
         "pre_validated" if summary["all_passed"] else "needs_attention",
         reusable, expiry, ocr_source, db._now(), user["id"]))
    audit("document", doc_id, user, "upload_prevalidate",
          "{}/{} checks passed (source: {}).".format(
              summary["checks_passed"], summary["checks_total"], ocr_source),
          {"doc_type": doc_type, "all_passed": summary["all_passed"]})

    return {
        "document_id": doc_id,
        "doc_type": doc_type,
        "label": spec["label"] if spec else doc_type,
        "ocr_source": ocr_source,
        "extracted_fields": fields,
        "checks": results,
        "summary": summary,
        "reusable": bool(reusable),
        "explainability": ("Every check above is a deterministic rule-table "
                           "validator — regex, hash comparison, expiry or "
                           "presence. No AI was involved in pass/fail."),
    }


@router.get("/documents/specs")
def document_specs(user: dict = Depends(get_current_user)):
    """Field declarations required per document type (drives the upload UI)."""
    specs = []
    for doc_type in sorted(rule_engine.list_doc_types()):
        spec = rule_engine.get_doc_spec(doc_type)
        specs.append({
            "doc_type": doc_type,
            "label": spec.get("label", doc_type),
            "extractable_fields": spec.get("extractable_fields", []),
        })
    return {"specs": specs,
            "note": ("Declared fields are validated by the same deterministic "
                     "rule-table checks as OCR-extracted ones.")}


@router.get("/documents/{document_id}")
def document_meta(document_id: str, user: dict = Depends(get_current_user)):
    doc = db.query_one("SELECT * FROM documents WHERE id=?", (document_id,))
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    _assert_doc_access(doc, user)
    doc["extracted_fields"] = db.jloads(doc["extracted_fields"], {})
    doc["validation_flags"] = db.jloads(doc["validation_flags"], [])
    return {"document": doc}


@router.get("/documents/{document_id}/file")
def download_document(document_id: str, user: dict = Depends(get_current_user)):
    from fastapi.responses import FileResponse
    doc = db.query_one("SELECT * FROM documents WHERE id=?", (document_id,))
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    _assert_doc_access(doc, user)
    path = config.UPLOAD_DIR / (doc["file_ref"] or "")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored file missing.")
    return FileResponse(str(path), media_type=doc["mime"] or "application/octet-stream",
                        filename=doc["filename"] or path.name)


def _assert_doc_access(doc: dict, user: dict) -> None:
    if user["role"] in ("officer", "admin"):
        return
    profile = db.query_one("SELECT owner_id FROM business_profiles WHERE id=?",
                           (doc["business_id"],))
    if not profile or profile["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not your document.")

