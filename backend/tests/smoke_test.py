"""End-to-end smoke test for the SIH26130 backend.

Run with the server up:  python backend/tests/smoke_test.py [base_url]
Covers: health, auth (RBAC), profile, rule-engine checklist, application
lifecycle, document upload + deterministic validation, green channel,
officer queue/decisions, admin analytics, Q&A.
"""
import hashlib
import io
import json
import sys
import urllib.request
import urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PAN = "ABCDE1234F"
GSTIN = "27" + PAN + "1Z5"  # 27 (MH) + 10-char PAN + entity 1 + Z + checksum 5
RESULTS = []


def call(method, path, token=None, body=None, raw=None, headers=None):
    url = BASE + path
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    if raw is not None:
        data = raw
    if token:
        hdrs["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read()
            try:
                return resp.status, json.loads(payload)
            except ValueError:
                return resp.status, payload
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode())
        except Exception:
            return exc.code, {}


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print("[{}] {} {}".format("PASS" if cond else "FAIL", name, extra))


def multipart(fields, files):
    boundary = "----sihboundary1234567890"
    buf = io.BytesIO()
    for key, value in fields.items():
        buf.write("--{}\r\nContent-Disposition: form-data; name=\"{}\"\r\n\r\n{}\r\n"
                  .format(boundary, key, value).encode())
    for key, (filename, content, ctype) in files.items():
        buf.write("--{}\r\nContent-Disposition: form-data; name=\"{}\"; filename=\"{}\"\r\n"
                  "Content-Type: {}\r\n\r\n".format(boundary, key, filename, ctype).encode())
        buf.write(content)
        buf.write(b"\r\n")
    buf.write("--{}--\r\n".format(boundary).encode())
    return buf.getvalue(), {"Content-Type": "multipart/form-data; boundary=" + boundary}


def doc_text(fields):
    return "\n".join("{}: {}".format(k, v) for k, v in fields.items()).encode()


def register_and_login(phone, email, role):
    call("POST", "/auth/register", body={
        "name": "Test " + role, "phone": phone, "email": email,
        "password": "Test@12345", "role": role, "invite_code": "MAHARASHTRA-2026"})
    _, login = call("POST", "/auth/login", body={
        "identifier": phone, "password": "Test@12345"})
    return login.get("token", "")


def main():
    # --- health ---
    status, health = call("GET", "/health")
    check("health", status == 200, str(health.get("status")))

    # --- register + login applicant ---
    status, reg = call("POST", "/auth/register", body={
        "name": "Test Entrepreneur", "phone": "9111100001", "email": "test1@demo.in",
        "password": "Test@12345", "role": "applicant"})
    check("register applicant", status in (200, 409), str(status))
    status, login = call("POST", "/auth/login", body={
        "identifier": "9111100001", "password": "Test@12345"})
    check("login applicant", status == 200 and login.get("token"))
    tok = login.get("token", "")

    # --- RBAC: applicant must NOT access officer/admin endpoints ---
    status, _ = call("GET", "/officer/queue", token=tok)
    check("RBAC blocks applicant from officer queue", status == 403)
    status, _ = call("GET", "/admin/analytics/summary", token=tok)
    check("RBAC blocks applicant from admin", status == 403)

    # --- officer register: invite code required ---
    status, _ = call("POST", "/auth/register", body={
        "name": "Test Officer", "phone": "9111100002", "email": "off1@demo.in",
        "password": "Test@12345", "role": "officer", "invite_code": "WRONG"})
    check("officer register without invite code rejected", status == 403)
    off_tok = register_and_login("9111100002", "off1@demo.in", "officer")
    check("officer register with invite code", bool(off_tok))

    # --- profile with PAN/GST ---
    profile_payload = {
        "name": "Sunrise Foods Pvt Ltd", "sector": "food_processing",
        "district": "Pune", "industrial_zone": "MIDC Chakan",
        "investment_size": 5000000, "employee_count": 25,
        "project_stage": "under_construction", "authorized_person": "A. Kumar",
        "pan": PAN, "gst": GSTIN, "registration_no": "REG-2024-001",
    }
    status, prof = call("POST", "/profiles", token=tok, body=profile_payload)
    check("create profile", status == 200, str(status))
    status, me = call("GET", "/profiles/me", token=tok)
    check("profile masked PAN",
          me.get("profile", {}).get("pan_masked", "").endswith(PAN[-4:]))

    # --- deterministic checklist ---
    status, checklist = call("GET", "/rule-engine/checklist", token=tok)
    codes = [a["code"] for a in checklist.get("approvals", [])]
    check("checklist has FSSAI-BASIC (green channel)", "FSSAI-BASIC" in codes)
    check("conditional SHOP-EST included (25 employees)", "SHOP-EST" in codes)
    check("parallel groups present", bool(checklist.get("parallel_groups")))

    # determinism: same input -> same output
    _, ev1 = call("POST", "/rule-engine/evaluate", body=profile_payload)
    _, ev2 = call("POST", "/rule-engine/evaluate", body=profile_payload)
    check("rule engine deterministic", ev1 == ev2)

    # --- create application for FSSAI (green-channel eligible) ---
    status, app = call("POST", "/applications", token=tok, body={
        "approval_id": "FSSAI-BASIC"})
    app_id = app.get("application_id", "")
    check("create application", status == 201 and bool(app_id))

    # --- upload documents (declared demo fields) ---
    pan_fields = {"entity_name": "Sunrise Foods Pvt Ltd", "pan_number": PAN}
    body, hdrs = multipart(
        {"application_id": app_id, "doc_type": "pan_card",
         "extracted_fields_json": json.dumps(pan_fields)},
        {"file": ("pan_card.txt", doc_text(pan_fields), "text/plain")})
    status, up1 = call("POST", "/documents/upload", token=tok, raw=body, headers=hdrs)
    check("upload PAN passes all checks", status == 200 and
          up1.get("summary", {}).get("all_passed"), json.dumps(up1.get("summary", {})))

    gst_fields = {"legal_name": "Sunrise Foods Pvt Ltd", "gstin": GSTIN,
                  "operating_address": "Plot 12, MIDC Chakan, Pune 410501"}
    body, hdrs = multipart(
        {"application_id": app_id, "doc_type": "gst_certificate",
         "extracted_fields_json": json.dumps(gst_fields)},
        {"file": ("gst.txt", doc_text(gst_fields), "text/plain")})
    status, up2 = call("POST", "/documents/upload", token=tok, raw=body, headers=hdrs)
    check("upload GST passes all checks (incl. PAN cross-link)",
          status == 200 and up2.get("summary", {}).get("all_passed"),
          json.dumps(up2.get("checks", [])))

    # Must match the server's canonical sha256_hex: strip().upper() before hashing.
    dec_hash = hashlib.sha256(
        "Sunrise Foods Pvt Ltd|{}".format(PAN).strip().upper().encode()).hexdigest()
    dec_fields = {"entity_name": "Sunrise Foods Pvt Ltd", "pan_number": PAN,
                  "form_hash": dec_hash, "aadhaar_otp_verified": "true"}
    body, hdrs = multipart(
        {"application_id": app_id, "doc_type": "self_declaration",
         "extracted_fields_json": json.dumps(dec_fields)},
        {"file": ("declaration.txt", doc_text(dec_fields), "text/plain")})
    status, up3 = call("POST", "/documents/upload", token=tok, raw=body, headers=hdrs)
    check("upload declaration passes integrity hash",
          status == 200 and up3.get("summary", {}).get("all_passed"),
          json.dumps(up3.get("checks", [])))

    # security: spoofed executable must be rejected by magic-byte check
    body, hdrs = multipart(
        {"application_id": app_id, "doc_type": "pan_card",
         "extracted_fields_json": json.dumps(pan_fields)},
        {"file": ("evil.exe", b"MZ\x90\x00" + b"A" * 100, "application/octet-stream")})
    status, _ = call("POST", "/documents/upload", token=tok, raw=body, headers=hdrs)
    check("magic-byte spoof rejected", status in (415, 400, 413))

    # --- readiness ---
    status, readiness = call("GET", "/applications/{}/readiness".format(app_id), token=tok)
    check("readiness computed 100", status == 200 and readiness.get("score") == 100.0,
          str(readiness.get("score")))
    check("readiness is explainable (breakdown present)",
          len(readiness.get("breakdown", [])) == 3)

    # --- submit -> green channel should fire ---
    status, sub = call("POST", "/applications/{}/submit".format(app_id), token=tok)
    gc = sub.get("green_channel", {})
    check("green channel issued on 100% pass", gc.get("issued") is True,
          str(gc.get("reason")))
    cert = gc.get("certificate") or sub.get("application", {}).get(
        "provisional_certificate")
    check("provisional certificate present (not final approval)",
          bool(cert) and "PROVISIONAL" in str(cert.get("type", "")))
    status, detail = call("GET", "/applications/{}".format(app_id), token=tok)
    inspections = detail.get("inspections", [])
    check("mandatory post-facto audit auto-created",
          any(i.get("is_post_facto_audit") for i in inspections))

    # --- RAG Q&A ---
    status, qa = call("GET", "/qa/ask?q=What%20approvals%20for%20a%20food%20processing%20factory%3F",
                      token=tok)
    check("RAG Q&A grounded with citations",
          status == 200 and qa.get("grounded") and bool(qa.get("citations")))
    status, qa2 = call("GET", "/qa/ask?q=quantum%20chromodynamics%20xylophone",
                       token=tok)
    check("Q&A refuses when not in rule set", status == 200 and not qa2.get("grounded"))

    # --- schemes ---
    status, schemes = call("GET", "/schemes/recommendations", token=tok)
    check("scheme recommendations returned", status == 200 and
          any(s["id"] == "sch_food_park" for s in schemes.get("eligible", [])))

    # --- officer flow on a second (non-green-channel) application ---
    status, app2 = call("POST", "/applications", token=tok, body={
        "approval_id": "MPCB-CTE"})
    app2_id = app2.get("application_id", "")
    call("POST", "/applications/{}/submit".format(app2_id), token=tok)
    status, queue = call("GET", "/officer/queue", token=off_tok)
    ids = [a["id"] for a in queue.get("unassigned", [])] + \
          [a["id"] for a in queue.get("assigned", [])]
    check("officer queue shows submitted app", app2_id in ids)
    status, pres = call("GET", "/officer/applications/{}/pre-scrutiny".format(app2_id),
                        token=off_tok)
    check("pre-scrutiny has AI + deterministic separation",
          "ai_summary" in pres and "deterministic_data" in pres)
    status, draft = call("POST", "/officer/applications/{}/draft-clarification".format(
        app2_id), token=off_tok)
    check("AI clarification draft returned (not sent)",
          status == 200 and bool(draft.get("draft")))
    status, dec = call("POST", "/officer/applications/{}/decision".format(app2_id),
                       token=off_tok,
                       body={"action": "clarify",
                             "clarification_text": "Please provide the lease deed.",
                             "notes": "AI draft used as base."})
    check("clarify decision creates request", status == 200 and
          dec.get("status") == "clarification_pending")
    status, _ = call("POST", "/officer/applications/{}/decision".format(app2_id),
                     token=off_tok, body={"action": "approve", "notes": "ok"})
    check("approve blocked while clarification open", status == 409)
    status, resp = call("POST", "/applications/{}/clarifications/{}/respond".format(
        app2_id, dec.get("clarification_id")), token=tok,
        body={"response": "Lease deed attached with the corrected plot number."})
    check("applicant responds to clarification", status == 200)
    status, dec2 = call("POST", "/officer/applications/{}/decision".format(app2_id),
                        token=off_tok, body={"action": "approve", "notes": "All clear."})
    check("officer approves (decision_source=human)", status == 200 and
          dec2.get("decision_source") == "human")

    # --- admin analytics + audit + toggle ---
    adm_tok = register_and_login("9111100003", "adm1@demo.in", "admin")
    status, summary = call("GET", "/admin/analytics/summary", token=adm_tok)
    check("admin analytics", status == 200 and summary.get("kpis", {}).get(
        "green_channel_certificates", 0) >= 1)
    status, auditlog = call("GET", "/admin/audit-log", token=adm_tok)
    sys_entries = [r for r in auditlog.get("audit_log", [])
                   if r.get("decision_source") == "system"]
    check("audit trail has system-sourced green channel entry", len(sys_entries) >= 1)
    call("POST", "/admin/green-channel/toggle", token=adm_tok, body={"enabled": False})
    status, gcs = call("GET", "/officer/green-channel/status", token=off_tok)
    check("admin can disable green channel globally", gcs.get("enabled") is False)
    call("POST", "/admin/green-channel/toggle", token=adm_tok, body={"enabled": True})

    print("\n{}/{} checks passed.".format(
        sum(1 for _, ok in RESULTS if ok), len(RESULTS)))
    if not all(ok for _, ok in RESULTS):
        sys.exit(1)


if __name__ == "__main__":
    main()



