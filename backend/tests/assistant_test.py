"""End-to-end test for the assistant chatbot (run against a live server)."""
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"


def call(method, path, payload=None, token=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + token} if token else {})},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


status, body = call("POST", "/auth/login",
                    {"identifier": "punefoods@demo.in", "password": "Foods@2026"})
assert status == 200, (status, body)
token = json.loads(body)["token"]
print("login OK")

status, body = call("POST", "/assistant/chat",
                    {"message": "What mistakes did my application make?"}, token)
assert status == 200, (status, body)
j = json.loads(body)
print("chat OK | intent={} ai={} issues={} session={}".format(
    j["intent"], j["ai_generated"], len(j["issues"]), j["session_id"]))
print("reply:", j["reply"][:220].replace("\n", " | "))

status, body = call("POST", "/assistant/stream",
                    {"message": "what is my application status",
                     "session_id": j["session_id"]}, token)
assert status == 200, (status, body)
assert "data:" in body and '"delta"' in body, body[:200]
assert '"done"' in body, body[-200:]
print("stream OK | events:", body.count("data:"))

sid = j["session_id"]
status, body = call("GET", "/assistant/history?session_id=" + sid, None, token)
assert status == 200, (status, body)
n = len(json.loads(body)["messages"])
assert n >= 4, n
print("history OK | msgs:", n)

status, _ = call("GET", "/assistant/history?session_id=" + sid)
assert status in (401, 403), status
print("auth-enforcement OK (unauthenticated history rejected:", status, ")")

print("\nALL ASSISTANT TESTS PASSED")
