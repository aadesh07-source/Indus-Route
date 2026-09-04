"""End-to-end test: Auto-Form Pipeline.

DigiLocker e-KYC -> Unified PDF form -> instant submit -> officer sees it
immediately -> all-green statutory checklist -> 1-click approve.

Run with the server up:  python backend/tests/autofill_test.py [base_url]
"""
import hashlib
import json
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from smoke_test import call, multipart, doc_text, check, RESULTS, PAN  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
GSTIN = "27" + PAN + "1Z5"
BUSINESS = "Pune Foods Pvt Ltd"


def main():
    # --- accounts ---
    status, login = call("POST", "/auth/login", body={
        "identifier": "9333300001", "password": "Test@12345"})
    if status != 200:
        call("POST", "/auth/register", body={
            "name": "Auto Fill", "phone": "9333300001", "email": "autofill@demo.in",
            "password": "Test@12345", "role": "applicant"})
        status, login = call("POST", "/auth/login", body={
            "identifier": "9333300001", "password": "Test@12345"})
    check("applicant login", status == 200 and login.get("token"))
    tok = login["token"]

    status, off = call("POST", "/auth/login", body={
        "identifier": "9111100002", "password": "Test@12345"})
    if status != 200:
        call("POST", "/auth/register", body={
            "name": "Test officer2", "phone": "9111100002",
            "email": "off2@demo.in", "password": "Test@12345",
            "role": "officer", "invite_code": "MAHARASHTRA-2026"})
        status, off = call("POST", "/auth/login", body={
            "identifier": "9111100002", "password": "Test@12345"})
    check("officer login", status == 200 and off.get("token"))
    otok = off["token"]

    # admin toggles Green Channel OFF so the officer-approval path is exercised
    status, adm = call("POST", "/auth/login", body={
        "identifier": "9111100003", "password": "Test@12345"})
    if status != 200:
        call("POST", "/auth/register", body={
            "name": "Test admin2", "phone": "9111100003", "email": "adm2@demo.in",
            "password": "Test@12345", "role": "admin",
            "invite_code": "MAHARASHTRA-2026"})
        status, adm = call("POST", "/auth/login", body={
            "identifier": "9111100003", "password": "Test@12345"})
    check("admin login", status == 200 and adm.get("token"))
    atok = adm["token"]
    call("POST", "/admin/green-channel/toggle", token=atok, body={"enabled": False})

    # --- profile ---
    status, prof = call("POST", "/profiles", token=tok, body={
        "name": BUSINESS, "sector": "food_processing", "district": "Pune",
        "industrial_zone": "MIDC Chakan", "investment_size": 5000000,
        "employee_count": 25, "project_stage": "under_construction",
        "authorized_person": "A. Kumar", "pan": PAN, "gst": GSTIN})
    check("profile saved", status == 200)

    # --- DigiLocker consent -> OTP -> verify -> apply ---
    status, c = call("POST", "/digilocker/consent", token=tok, body={
        "aadhaar_number": "234123412346"})
    check("digilocker consent", status == 200 and c.get("demo_otp"),
          str(c.get("aadhaar_masked")))
    consent_id, otp = c["consent_id"], c["demo_otp"]

    status, _ = call("POST", "/digilocker/consent/{}/verify".format(consent_id),
                     token=tok, body={"otp": "000000"})
    check("wrong OTP rejected", status == 422)

    status, v = call("POST", "/digilocker/consent/{}/verify".format(consent_id),
                     token=tok, body={"otp": otp})
    check("OTP verified", status == 200 and v.get("verified", {}).get("verified"))

    status, a = call("POST", "/digilocker/consent/{}/apply".format(consent_id),
                     token=tok, body={"pan": PAN, "gst": GSTIN})
    check("e-KYC applied to profile", status == 200 and a.get("status") == "applied")

    # --- create application + generate form BEFORE docs ---
    status, app = call("POST", "/applications", token=tok, body={
        "approval_id": "FSSAI-BASIC"})
    app_id = app.get("application_id", "")
    check("application created", status == 201 and bool(app_id))

    status, form1 = call("POST", "/applications/{}/generate-form".format(app_id),
                         token=tok)
    check("form generated (pre-docs)", status == 200
          and form1.get("verification_code"))
    check("form is e-KYC bound", form1.get("kyc_bound") is True)
    vcode = form1["verification_code"]

    status, pdf = call("GET", "/applications/{}/form.pdf".format(app_id),
                       token=tok)
    check("form PDF downloads", status == 200 and bytes(pdf).startswith(b"%PDF-1.4"),
          "{} bytes".format(len(pdf)))

    status, ver = call("GET", "/forms/verify/{}".format(vcode))
    check("public verification valid", status == 200 and ver.get("valid") is True)

    # officer pre-scrutiny BEFORE docs must NOT be all-green
    status, pre = call("GET", "/officer/applications/{}/pre-scrutiny".format(app_id),
                       token=otok)
    check("pre-scrutiny detects missing docs",
          status == 200 and pre["one_click"]["all_green"] is False)

    # --- upload the three required demo documents ---
    pan_fields = {"entity_name": BUSINESS, "pan_number": PAN}
    body, hdrs = multipart(
        {"application_id": app_id, "doc_type": "pan_card",
         "extracted_fields_json": json.dumps(pan_fields)},
        {"file": ("pan_card.txt", doc_text(pan_fields), "text/plain")})
    status, up = call("POST", "/documents/upload", token=tok, raw=body, headers=hdrs)
    check("upload PAN", up.get("summary", {}).get("all_passed"))

    gst_fields = {"legal_name": BUSINESS, "gstin": GSTIN,
                  "operating_address": "Plot 12, MIDC Chakan, Pune 410501"}
    body, hdrs = multipart(
        {"application_id": app_id, "doc_type": "gst_certificate",
         "extracted_fields_json": json.dumps(gst_fields)},
        {"file": ("gst.txt", doc_text(gst_fields), "text/plain")})
    status, up = call("POST", "/documents/upload", token=tok, raw=body, headers=hdrs)
    check("upload GST", up.get("summary", {}).get("all_passed"))

    dec_hash = hashlib.sha256(
        "{}|{}".format(BUSINESS, PAN).strip().upper().encode()).hexdigest()
    dec_fields = {"entity_name": BUSINESS, "pan_number": PAN,
                  "form_hash": dec_hash, "aadhaar_otp_verified": "true"}
    body, hdrs = multipart(
        {"application_id": app_id, "doc_type": "self_declaration",
         "extracted_fields_json": json.dumps(dec_fields)},
        {"file": ("declaration.txt", doc_text(dec_fields), "text/plain")})
    status, up = call("POST", "/documents/upload", token=tok, raw=body, headers=hdrs)
    check("upload declaration", up.get("summary", {}).get("all_passed"))

    # regenerate the form so the PDF embeds the document matrix
    status, form2 = call("POST", "/applications/{}/generate-form".format(app_id),
                         token=tok)
    check("form regenerated with docs", status == 200)
    vcode = form2["verification_code"]  # latest form's code

    # --- instant submit via auto-form ---
    _, v0 = call("GET", "/officer/queue/version", token=otok)
    status, sub = call("POST", "/applications/{}/submit-form".format(app_id),
                       token=tok)
    check("submit-form accepted", status == 200,
          str(sub.get("application", {}).get("status")))
    check("instant dispatch confirmed", "Instant dispatch" in sub.get("dispatched", ""))
    _, v1 = call("GET", "/officer/queue/version", token=otok)
    check("queue version changed (poll signal)", v0["version"] != v1["version"])

    # --- officer sees it instantly + all-green matrix ---
    status, q = call("GET", "/officer/queue", token=otok)
    ids = [e["id"] for e in q.get("assigned", []) + q.get("unassigned", [])]
    check("application visible in officer queue", app_id in ids)

    status, pre = call("GET", "/officer/applications/{}/pre-scrutiny".format(app_id),
                       token=otok)
    check("all parameters green", pre["one_click"]["all_green"] is True)
    check("readiness 100", pre["one_click"]["readiness_100"] is True)
    check("form provenance shown", pre.get("form", {}).get("verification_code") == vcode)

    # --- 1-click approve ---
    status, dec = call("POST", "/officer/applications/{}/decision".format(app_id),
                       token=otok, body={
                           "action": "approve",
                           "notes": "1-click: all parameters verified green."})
    check("1-click approve", status == 200 and dec.get("status") == "approved")

    status, q = call("GET", "/officer/queue", token=otok)
    ids = [e["id"] for e in q.get("assigned", []) + q.get("unassigned", [])]
    check("approved application left the queue", app_id not in ids)

    # restore Green Channel global state for other flows
    call("POST", "/admin/green-channel/toggle", token=atok, body={"enabled": True})

    passed = sum(1 for _, ok in RESULTS if ok)
    print("\n{}/{} auto-form pipeline checks passed.".format(passed, len(RESULTS)))


if __name__ == "__main__":
    main()

