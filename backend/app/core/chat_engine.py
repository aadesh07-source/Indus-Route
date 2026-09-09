"""Applicant chat engine — real-time one-to-one assistant with live context.

PHILOSOPHY (mirrors ai_service.py): RULES DECIDE. AI EXPLAINS.
1. Deterministic data first — the applicant's latest application, failed
   document checks, missing required documents, open clarifications, decision
   feedback, readiness and SLA state are queried from SQLite.
2. Deterministic intent routing (keyword scoring) — no LLM in the routing path.
3. The LLM only EXPLAINS the gathered data, quarantined inside <user_data>
   (prompt-injection containment, same contract as ai_service). It can never
   change an outcome, invent requirements, or decide an approval.
4. Offline-safe: without GEMINI_API_KEY (or on any API error) deterministic
   template replies stream word-by-word, so the chat is fully functional.
5. Conversation memory persists per (user, session) in chat_messages — a user
   can only ever read their own session rows (enforced at the API layer).
"""
import json

from .. import db, config
from . import digilocker, regulatory_kb, rule_engine
from .ai_service import (INJECTION_GUARD, _gemini_available,
                         _call_gemini_stream, answer_regulatory_question)

try:
    from .readiness import sla_status
except Exception:  # pragma: no cover — readiness must never block chat
    sla_status = None

MAX_HISTORY_TURNS = 12
MAX_MESSAGE_CHARS = 1000

_DIAGNOSE_WORDS = ("mistake", "mistakes", "wrong", "reject", "rejected",
                   "refuse", "why", "issue", "problem", "fix", "stuck",
                   "fail", "failed", "returned", "send back", "sendback",
                   "incomplete", "error", "correction")
_DOCS_WORDS = ("document", "documents", "missing", "upload", "checklist",
               "required", "attach", "proof", "certif")
_STATUS_WORDS = ("status", "where is", "how long", "when will", "timeline",
                 "sla", "progress", "pending", "wait", "how much longer")

_FIX_HINTS = {
    "pan_hash": "Re-upload a clear PAN card — the PAN printed on it must match "
                "the PAN saved in your business profile exactly.",
    "entity_name_match": "The entity name on the document differs from your "
                         "registered business name — re-upload with the correct name.",
    "gstin_pan_link": "Your GSTIN is not linked to the profile PAN. Verify the "
                      "GST certificate or correct the PAN/GST fields in your profile.",
    "date_valid": "The document appears expired — upload the latest issue.",
    "date_after": "The document date is earlier than required — upload the "
                  "latest issued version.",
}


def _classify_intent(message: str) -> str:
    """Deterministic keyword scoring. diagnose > documents > status > general."""
    text = (message or "").lower()
    d = sum(1 for w in _DIAGNOSE_WORDS if w in text)
    o = sum(1 for w in _DOCS_WORDS if w in text)
    s = sum(1 for w in _STATUS_WORDS if w in text)
    if d >= 1 and d >= o and d >= s:
        return "diagnose"
    if o >= 1 and o >= s:
        return "documents"
    if s >= 1:
        return "status"
    return "general"


def _app_documents(application_id: str) -> list:
    rows = db.query("SELECT * FROM documents WHERE application_id=? "
                    "ORDER BY uploaded_at", (application_id,))
    for r in rows:
        r["extracted_fields"] = db.jloads(r.get("extracted_fields"), {})
        r["validation_flags"] = db.jloads(r.get("validation_flags"), [])
    return rows


def _latest_application(user_id: str):
    row = db.query_one(
        "SELECT a.*, ap.name AS approval_name, ap.code AS approval_code, "
        "ap.department, ap.sla_days, ap.required_documents "
        "FROM applications a "
        "JOIN approvals ap ON ap.id = a.approval_id "
        "JOIN business_profiles bp ON bp.id = a.business_id "
        "WHERE bp.owner_id=? ORDER BY a.created_at DESC LIMIT 1", (user_id,))
    return dict(row) if row else None


def build_diagnosis(app_row, documents: list) -> list:
    """Deterministic list of concrete issues — the ground truth the AI explains."""
    issues = []
    if app_row is None:
        return issues
    for doc in documents:
        label = doc.get("label") or doc.get("type") or "document"
        for flag in doc.get("validation_flags") or []:
            if not flag.get("passed", False):
                cid = flag.get("check_id", "unknown")
                issues.append({
                    "issue_type": "failed_document_check",
                    "document": label,
                    "check_id": cid,
                    "reason": (flag.get("reason", "") or "")[:200],
                    "how_to_fix": _FIX_HINTS.get(
                        cid, "Re-upload a corrected document — the same check "
                             "re-runs automatically on upload."),
                })
    # Missing required documents.
    have = {d.get("type") for d in documents}
    for req in db.jloads(app_row.get("required_documents"), []):
        rtype = req.get("type") if isinstance(req, dict) else req
        if rtype and rtype not in have:
            spec = rule_engine.get_doc_spec(rtype)
            label = spec.get("label", rtype) if isinstance(spec, dict) else rtype
            issues.append({
                "issue_type": "missing_document",
                "document": label,
                "check_id": "doc_present",
                "reason": "Required document '{}' has not been uploaded yet.".format(label),
                "how_to_fix": "Upload it from the Upload Centre — it is "
                              "pre-validated by the same statutory checks.",
            })
    # Open clarifications from the officer.
    for c in db.query("SELECT final_text FROM clarification_requests "
                      "WHERE application_id=? AND status='open'",
                      (app_row["id"],)):
        issues.append({
            "issue_type": "open_clarification",
            "document": "officer request",
            "check_id": "clarification_response",
            "reason": (c.get("final_text", "") or "")[:200],
            "how_to_fix": "Respond from the Application tab — processing resumes "
                          "once the clarification is answered.",
        })
    # Rejection / send-back feedback.
    if app_row.get("status") in ("rejected", "returned") and app_row.get("feedback"):
        issues.append({
            "issue_type": "decision_feedback",
            "document": "decision",
            "check_id": "officer_feedback",
            "reason": (app_row.get("feedback") or "")[:300],
            "how_to_fix": "Address the officer's feedback, then resubmit the "
                          "application.",
        })
    return issues


def gather_context(user: dict) -> dict:
    """Everything the assistant may truthfully say about THIS applicant."""
    profile = db.query_one("SELECT * FROM business_profiles WHERE owner_id=?",
                           (user["id"],))
    app_row = _latest_application(user["id"])
    documents = _app_documents(app_row["id"]) if app_row else []
    issues = build_diagnosis(app_row, documents)
    sla = None
    if app_row and sla_status:
        try:
            sla = sla_status(app_row)
        except Exception:
            sla = None
    return {
        "business": ({
            "name": profile["name"], "sector": profile["sector"],
            "district": profile["district"], "zone": profile["industrial_zone"],
            "investment": profile["investment_size"],
            "employees": profile["employee_count"],
            "stage": profile["project_stage"],
        } if profile else None),
        "application": ({
            "approval": "{} ({}, {})".format(app_row.get("approval_name"),
                                             app_row.get("approval_code"),
                                             app_row.get("department")),
            "status": app_row.get("status"),
            "readiness_score": app_row.get("readiness_score"),
            "sla": sla,
            "decision_notes": (app_row.get("decision_notes") or "")[:300],
        } if app_row else None),
        "documents_uploaded": [
            {"label": d.get("label") or d.get("type"),
             "status": d.get("status"),
             "checks_passed": d.get("checks_passed"),
             "checks_total": d.get("checks_total")}
            for d in documents
        ],
        "issues_found": issues,
        "kyc_verified": bool(digilocker.latest_verified(user["id"])),
    }


# ───────────────────────────────────────────── conversation memory (persisted)

def load_history(user_id: str, session_id: str) -> list:
    rows = db.query(
        "SELECT role, content FROM chat_messages WHERE user_id=? AND session_id=? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, session_id, MAX_HISTORY_TURNS * 2))
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def save_message(user_id: str, session_id: str, role: str, content: str,
                 intent: str = "", citations=None) -> None:
    db.execute(
        "INSERT INTO chat_messages (id, user_id, session_id, role, content, "
        "intent, citations, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (db.new_id("msg"), user_id, session_id, role, content[:4000],
         intent, db.jdumps(citations or []), db._now()))


def history(user: dict, session_id: str) -> list:
    if not session_id:
        return []
    rows = db.query(
        "SELECT role, content, intent, citations, created_at FROM chat_messages "
        "WHERE user_id=? AND session_id=? ORDER BY created_at",
        (user["id"], session_id))
    return [{"role": r["role"], "content": r["content"],
             "intent": r.get("intent", ""),
             "citations": db.jloads(r.get("citations"), []),
             "created_at": r.get("created_at")} for r in rows]


# ────────────────────────────────────────────────────── deterministic fallbacks

def _dedupe_statutes(statutes: list) -> list:
    """Keep the top hit per distinct statute title."""
    seen, out = set(), []
    for s in statutes:
        key = s.get("title", "")
        if key and key not in seen:
            seen.add(key)
            out.append(s)
    return out


def _rank_statutes(statutes: list, sector: str) -> list:
    """Stable sort: docs mentioning the applicant's own sector rank first."""
    if not sector:
        return statutes
    needle = sector.replace("_", " ").lower()
    return sorted(statutes, key=lambda s: 0 if needle in (s.get("text") or "").lower() else 1)


def _statute_fallback(statutes: list):
    """Grounded deterministic answer from the vector-retrieved statutes."""
    if not statutes:
        return None
    lines = ["Based on the **statutory knowledge base**, the most relevant "
             "requirement(s) for your question:", ""]
    for i, s in enumerate(statutes, 1):
        lines.append("{}. **{}**".format(i, s["title"]))
        if s.get("source"):
            lines.append("   → **Statute:** {}".format(s["source"]))
        lines.append("   {}".format((s.get("text") or "")[:240]))
    lines.append("")
    lines.append("*Advisory only — verify with the issuing department.*")
    return "\n".join(lines)


def _status_line(ctx: dict) -> str:
    app = ctx.get("application")
    if not app:
        return ("**No application yet.** Create one from the Application tab "
                "after completing your business profile — I can then guide you "
                "through every approval it needs.")
    sla = app.get("sla") or {}
    sla_txt = ""
    if sla.get("state") == "breached":
        sla_txt = " ⚠ **SLA breached.**"
    elif sla.get("remaining_hours") is not None:
        sla_txt = " **{}h** of SLA remaining.".format(int(sla["remaining_hours"]))
    return ("Application **{}** is **{}** — readiness **{}/100**.{}".format(
        app.get("approval"), app.get("status"),
        int(app.get("readiness_score") or 0), sla_txt))


def _fallback_reply(intent: str, ctx: dict) -> str:
    if intent == "diagnose":
        issues = ctx.get("issues_found") or []
        if not issues:
            return ("**Good news — no issues found.** No failing checks or missing "
                    "documents were detected on your latest application.\n\n"
                    + _status_line(ctx))
        lines = ["I found **{} issue(s)** in your latest application:".format(len(issues)), ""]
        for i, issue in enumerate(issues, 1):
            label = issue["issue_type"].replace("_", " ").title()
            lines.append("{}. **{}** — {}".format(
                i, label, issue["reason"] or issue["document"]))
            lines.append("   → **Fix:** {}".format(issue["how_to_fix"]))
        lines.append("")
        lines.append("**What happens next:** fix these and your readiness score "
                     "updates instantly — the officer sees the same deterministic "
                     "checks during review.")
        return "\n".join(lines)
    if intent == "status":
        return _status_line(ctx) + "\n\n*Advisory only — the officer makes every decision.*"
    if intent == "documents":
        missing = [i for i in (ctx.get("issues_found") or [])
                   if i["issue_type"] in ("missing_document", "failed_document_check")]
        if not missing:
            return ("**All documents in order.** Every required document for your "
                    "latest application is uploaded and passing its checks.\n\n"
                    + _status_line(ctx))
        lines = ["**These documents need your attention:**", ""]
        for i, issue in enumerate(missing, 1):
            lines.append("{}. **{}**".format(i, issue["document"]))
            lines.append("   → **Fix:** {}".format(issue["how_to_fix"]))
        return "\n".join(lines)
    return ("I can answer questions about approvals, documents and your "
            "application status. Try one of these:\n\n"
            "- \"Why was my application returned?\"\n"
            "- \"What documents am I missing?\"\n"
            "- \"Which MPCB consent do I need before construction?\"")


def _build_prompt(message: str, history_turns: list, ctx: dict,
                  statutes: list = None) -> str:
    system = (INJECTION_GUARD +
              "You are IndusRoute Assistant, a one-to-one helper for an "
              "applicant on a government industrial-approval portal. Be warm, "
              "specific, and under 160 words. Use ONLY live_application_context "
              "for anything about their application and ONLY statutory_context "
              "for legal/regulatory claims — never invent facts, approvals, "
              "forms or deadlines. When statutory_context contains relevant "
              "entries, cite the statute title(s) inline. If the retrieved "
              "statutes do not cover the question, say so and advise contacting "
              "the issuing department. For diagnosis questions, list each issue "
              "and its how_to_fix exactly. End with one concrete next step. "
              "You never decide approvals — officers do.")
    history_txt = "\n".join("{}: {}".format(t["role"], t["content"][:400])
                            for t in history_turns) or "(new conversation)"
    statute_txt = "\n".join(
        "- [{}] {} :: {}".format(i, s["title"], (s.get("text") or "")[:420])
        for i, s in enumerate(statutes or [], 1)) or "(none retrieved)"
    return (
        "{}\n<user_data>\nlive_application_context: {}\n"
        "statutory_context (retrieved via vector search):\n{}\n"
        "conversation_history:\n{}\napplicant_message: {}\n</user_data>\n\n"
        "Answer the applicant's message using ONLY live_application_context "
        "for application facts and statutory_context for regulation claims."
    ).format(system, json.dumps(ctx, ensure_ascii=False, default=str),
             statute_txt, history_txt, message)


# ─────────────────────────────────────────────────────────────── public API

def respond(user: dict, message: str, session_id: str = "") -> dict:
    """Non-streaming reply. Hybrid RAG: vector statutes + live applicant
    context -> Gemini (streaming endpoint, collected) -> deterministic fallback."""
    message = (message or "").strip()[:MAX_MESSAGE_CHARS]
    session_id = session_id or db.new_id("chs")
    ctx = gather_context(user)
    intent = _classify_intent(message)
    sector = (ctx.get("business") or {}).get("sector") or ""
    statutes = _rank_statutes(
        _dedupe_statutes(
            regulatory_kb.retrieve((message + " " + sector.replace("_", " ")
                                + " sector") if sector else message, n=8) if message else []), sector)[:3]
    citations = [{"title": s["title"], "source": s["source"]} for s in statutes]
    ai_generated = False
    reply_text = ""

    if message and _gemini_available():
        try:
            prompt = _build_prompt(message,
                                   load_history(user["id"], session_id),
                                   ctx, statutes)
            reply_text = "".join(_call_gemini_stream(prompt)).strip()
            ai_generated = bool(reply_text)
        except Exception:
            reply_text = ""
            ai_generated = False

    if not ai_generated:
        if intent == "general" and message:
            reply_text = (_statute_fallback(statutes)
                          or (answer_regulatory_question(message).get("answer", "")
                              if message else "") or _fallback_reply(intent, ctx))
        else:
            reply_text = _fallback_reply(intent, ctx)

    save_message(user["id"], session_id, "user", message, intent)
    save_message(user["id"], session_id, "assistant", reply_text, intent, citations)
    return {"session_id": session_id, "reply": reply_text, "intent": intent,
            "citations": citations, "issues": ctx.get("issues_found") or [],
            "ai_generated": ai_generated}


def _sse(data: dict) -> str:
    return "data: {}\n\n".format(json.dumps(data, ensure_ascii=False, default=str))


def stream_reply(user: dict, message: str, session_id: str = ""):
    """SSE generator: {"delta": ...} chunks, then one final {"done": ...} event.

    Pipeline: live application context + vector-search statutes + conversation
    memory -> Gemini token streaming -> deterministic fallback if unavailable.
    """
    message = (message or "").strip()[:MAX_MESSAGE_CHARS]
    session_id = session_id or db.new_id("chs")
    ctx = gather_context(user)
    intent = _classify_intent(message)
    sector = (ctx.get("business") or {}).get("sector") or ""
    statutes = _rank_statutes(
        _dedupe_statutes(
            regulatory_kb.retrieve((message + " " + sector.replace("_", " ")
                                + " sector") if sector else message, n=8) if message else []), sector)[:3]
    citations = [{"title": s["title"], "source": s["source"]} for s in statutes]
    yield _sse({"session_id": session_id, "intent": intent, "start": True,
                "statutes": [s["title"] for s in statutes]})

    stream = None
    if message and _gemini_available():
        try:
            prompt = _build_prompt(message,
                                   load_history(user["id"], session_id),
                                   ctx, statutes)
            stream = _call_gemini_stream(prompt)
        except Exception:
            stream = None

    full: list = []
    if stream is not None:
        try:
            for chunk in stream:
                full.append(chunk)
                yield _sse({"delta": chunk})
        except Exception:
            full = []

    if not full:
        if intent == "general" and message:
            fallback = (_statute_fallback(statutes)
                        or answer_regulatory_question(message).get("answer", "")
                        or _fallback_reply(intent, ctx))
        else:
            fallback = _fallback_reply(intent, ctx)
        # Deterministic fallback streams word-by-word (real-time feel, offline).
        for word in fallback.split(" "):
            yield _sse({"delta": word + " "})
        full = [fallback]

    reply_text = "".join(full).strip() or "Could not generate a reply — try again."
    save_message(user["id"], session_id, "user", message, intent)
    save_message(user["id"], session_id, "assistant", reply_text, intent, citations)
    yield _sse({"done": True, "session_id": session_id, "intent": intent,
                "citations": citations, "issues": ctx.get("issues_found") or [],
                "ai_generated": True,
                "mode": "gemini-flash+chromadb" if statutes and full != [fallback]
                        else ("gemini-flash" if full != [fallback]
                              else "deterministic-fallback")})