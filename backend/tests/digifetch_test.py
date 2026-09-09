import json, urllib.request, sys
BASE = "http://127.0.0.1:8000"
ok = []

def call(method, path, payload=None, token=None, raw=False):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body or b"{}"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

# 1. login
s, r = call("POST", "/auth/login", {"identifier": "9000000001", "password": "Foods@2026"})
tok = r.get("token")
ok.append(("login", s == 200 and bool(tok)))

# 2. list applications
s, r = call("GET", "/applications", token=tok)
apps = r.get("applications", [])
app = next((a for a in apps if a.get("status") in ("draft", "returned")), apps[0] if apps else None)
ok.append(("list apps", s == 200 and app is not None))

if app:
    aid = app["id"]
    # 3. fetchable docs picker
    s, r = call("GET", f"/digilocker/fetchable?application_id={aid}", token=tok)
    docs = r.get("docs", [])
    digi_types = [d["type"] for d in docs if d.get("digilocker_issued") and d.get("status") == "pending"]
    ok.append(("fetchable picker", s == 200 and len(docs) > 0 and r.get("mode") == "sandbox"))
    print("picker docs:", [(d["type"], d["digilocker_issued"], d["status"]) for d in docs])

    # 4. fetch DigiLocker issued docs
    if digi_types:
        s, r = call("POST", "/digilocker/fetch-documents",
                    {"application_id": aid, "doc_types": digi_types}, token=tok)
        fetched = r.get("fetched", [])
        passed = all(f["summary"]["all_passed"] for f in fetched) if fetched else True
        ok.append(("fetch-documents", s == 200 and r.get("docs_registered") == len(digi_types) and passed))
        for f in fetched:
            print("  fetched:", f["type"], f["issuer"], f["summary"]["checks_passed"], "/", f["summary"]["checks_total"])
        print("  still_pending:", r.get("still_pending"))
    else:
        ok.append(("fetch-documents", True))
        print("  no pending digilocker docs (all already registered)")

    # 5. form.pdf auto-generates + serves
    s, raw = call("GET", f"/applications/{aid}/form.pdf", token=tok, raw=True)
    ok.append(("form.pdf served", s == 200 and raw[:4] == b"%PDF"))
    print("  form.pdf:", len(raw), "bytes, %PDF signature:", raw[:4] == b"%PDF")

# 6. RBAC: other user cannot fetch
s2, r2 = call("POST", "/auth/login", {"identifier": "9000000011", "password": "Pharma@2026"})
tok2 = r2.get("token")
if app:
    s, r = call("POST", "/digilocker/fetch-documents",
                {"application_id": app["id"], "doc_types": ["pan_card"]}, token=tok2)
    ok.append(("RBAC cross-user blocked", s == 403))
    print("  cross-user fetch status:", s)

print()
allok = all(v for _, v in ok)
for name, v in ok: print(("PASS" if v else "FAIL"), name)
print()
print("ALL DIGILOCKER FETCH TESTS PASSED" if allok else "SOME TESTS FAILED")
sys.exit(0 if allok else 1)