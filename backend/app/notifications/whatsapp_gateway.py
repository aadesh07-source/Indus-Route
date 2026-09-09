"""INDUS ROUTE - Twilio WhatsApp gateway (production, WhatsApp-only)."""
from __future__ import annotations

import json
import logging
import re

from .. import config
from .. import db

logger = logging.getLogger(__name__)

_GATEWAY_STATE = {"whatsapp_sent": 0, "whatsapp_failed": 0, "logged": 0}
_twilio_client = None
_twilio_client_key = ""


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalise_phone_e164(phone: str, default_country: str = "91") -> str:
    """Normalise to +E.164. Accepts 9326166814, 09326166814, 919326166814."""
    raw = str(phone or "").strip()
    if raw.lower().startswith("whatsapp:"):
        raw = raw[len("whatsapp:"):].strip()
    if raw.startswith("+"):
        digits = _digits_only(raw)
        return "+" + digits if digits else ""
    digits = _digits_only(raw)
    if not digits:
        return ""
    if digits.startswith("00"):
        return "+" + digits[2:]
    if len(digits) == 12 and digits.startswith(default_country):
        return "+" + digits
    if len(digits) == 11 and digits.startswith("0"):
        return "+" + default_country + digits[1:]
    if len(digits) == 10:
        return "+" + default_country + digits
    if len(digits) > 10:
        return "+" + digits
    return ""


def to_whatsapp(phone: str) -> str:
    raw = str(phone or "").strip()
    if raw.lower().startswith("whatsapp:"):
        e164 = normalise_phone_e164(raw[len("whatsapp:"):])
    else:
        e164 = normalise_phone_e164(raw)
    return ("whatsapp:" + e164) if e164 else ""


def normalise_sender(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("whatsapp:"):
        inner = raw[len("whatsapp:"):].strip()
        if inner.startswith("+"):
            return "whatsapp:" + inner
        digits = _digits_only(inner)
        return ("whatsapp:+" + digits) if digits else ""
    if raw.startswith("+"):
        return "whatsapp:" + raw
    digits = _digits_only(raw)
    return ("whatsapp:+" + digits) if digits else ""
def _creds_fingerprint() -> str:
    return "|".join([
        config.TWILIO_ACCOUNT_SID or "",
        config.TWILIO_AUTH_TOKEN or "",
        getattr(config, "TWILIO_API_KEY_SID", "") or "",
        getattr(config, "TWILIO_API_KEY_SECRET", "") or "",
    ])


def _get_twilio_client():
    global _twilio_client, _twilio_client_key
    try:
        from twilio.rest import Client  # type: ignore
    except ImportError:
        logger.warning("twilio package not installed - pip install twilio")
        return None
    if not config.TWILIO_ACCOUNT_SID:
        return None
    fingerprint = _creds_fingerprint()
    if _twilio_client is None or _twilio_client_key != fingerprint:
        api_sid = (getattr(config, "TWILIO_API_KEY_SID", "") or "").strip()
        api_secret = (getattr(config, "TWILIO_API_KEY_SECRET", "") or "").strip()
        try:
            if api_sid and api_secret:
                _twilio_client = Client(api_sid, api_secret, config.TWILIO_ACCOUNT_SID)
            elif config.TWILIO_AUTH_TOKEN:
                _twilio_client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
            else:
                return None
            _twilio_client_key = fingerprint
        except Exception as exc:
            logger.warning("Twilio client init failed: %s", exc)
            return None
    return _twilio_client


def _sender() -> str:
    # Try it out WhatsApp sandbox number for this trial account. If the user
    # has joined the sandbox (text "join <code>" to it from their phone) the
    # 24h customer-service window opens and pre-approved templates are allowed.
    return normalise_sender(config.TWILIO_WHATSAPP_FROM) or "whatsapp:+17372508034"


def _resolve_recipient(phone: str, user_id: str = "") -> str:
    wa = to_whatsapp(phone)
    if wa:
        return wa
    if user_id:
        try:
            urow = db.query_one("SELECT phone FROM users WHERE id=?", (user_id,))
            if urow and urow.get("phone"):
                wa = to_whatsapp(urow["phone"])
                if wa:
                    return wa
        except Exception:
            pass
    return to_whatsapp(getattr(config, "TWILIO_WHATSAPP_TO", "") or "")


def gateway_status() -> dict:
    return {
        "gateway": "twilio-whatsapp",
        "channel": "whatsapp",
        "brand": "INDUS ROUTE",
        "twilio_configured": bool(
            config.TWILIO_ACCOUNT_SID
            and (config.TWILIO_AUTH_TOKEN or getattr(config, "TWILIO_API_KEY_SECRET", ""))
        ),
        "auth_mode": (
            "api-key"
            if (getattr(config, "TWILIO_API_KEY_SID", "") and getattr(config, "TWILIO_API_KEY_SECRET", ""))
            else ("account-token" if config.TWILIO_AUTH_TOKEN else "not-configured")
        ),
        "whatsapp_from": _sender(),
        "registered_phone": getattr(config, "TWILIO_FROM_NUMBER", "") or "",
        "sandbox_code": getattr(config, "TWILIO_SANDBOX_CODE", "") or "",
        "whatsapp_to_fallback": to_whatsapp(getattr(config, "TWILIO_WHATSAPP_TO", "") or "") or "(not set)",
        "templates_configured": {
            "generic": bool(getattr(config, "TWILIO_CONTENT_SID_GENERIC", "")),
            "otp": bool(getattr(config, "TWILIO_CONTENT_SID_OTP", "")),
            "submitted": bool(getattr(config, "TWILIO_CONTENT_SID_SUBMITTED", "")),
            "sanctioned": bool(getattr(config, "TWILIO_CONTENT_SID_SANCTIONED", "")),
            "sent_back": bool(getattr(config, "TWILIO_CONTENT_SID_SENTBACK", "")),
        },
        **_GATEWAY_STATE,
    }


def brand(body: str) -> str:
    text = str(body or "").strip()
    if not text:
        return text
    if text.upper().startswith("INDUS ROUTE"):
        return text[:1000]
    return ("INDUS ROUTE: " + text)[:1000]



def _template_for(body: str) -> str:
    upper = str(body or "").upper()
    cfg = config
    if "OTP" in upper and getattr(cfg, "TWILIO_CONTENT_SID_OTP", ""):
        return getattr(cfg, "TWILIO_CONTENT_SID_OTP")
    if "SUBMITTED SUCCESSFULLY" in upper and getattr(cfg, "TWILIO_CONTENT_SID_SUBMITTED", ""):
        return getattr(cfg, "TWILIO_CONTENT_SID_SUBMITTED", "")
    if ("SANCTIONED" in upper or "VERIFIED" in upper) and getattr(cfg, "TWILIO_CONTENT_SID_SANCTIONED", ""):
        return getattr(cfg, "TWILIO_CONTENT_SID_SANCTIONED", "")
    if ("RESUBMIT" in upper or "SENT BACK" in upper or "PARAMETERS REQUIRED" in upper) and getattr(cfg, "TWILIO_CONTENT_SID_SENTBACK", ""):
        return getattr(cfg, "TWILIO_CONTENT_SID_SENTBACK", "")
    return getattr(cfg, "TWILIO_CONTENT_SID_GENERIC", "") or ""


def _clean_twilio_error(exc: Exception) -> str:
    raw = str(exc)
    # Strip ANSI colour codes the twilio SDK embeds in console errors.
    raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:500]


def _needs_template_retry(error_text: str) -> bool:
    lowered = str(error_text or "").lower()
    for code in ("21654", "21659", "63016", "63015", "63007", "63027"):
        if code in lowered:
            return True
    if "contentsid" in lowered and "required" in lowered:
        return True
    return False


def _send_via_twilio(to_wa: str, body: str) -> dict:
    client = _get_twilio_client()
    if client is None:
        try:
            import twilio  # noqa: F401
        except ImportError:
            return {"ok": False, "error": "twilio_sdk_not_installed: pip install twilio"}
        return {"ok": False, "error": "twilio_not_configured"}
    from_wa = _sender()
    if not to_wa or not from_wa:
        return {"ok": False, "error": "whatsapp_number_missing"}
    # 1) First attempt: free-form Body. This works for the Twilio WhatsApp
    #    sandbox once the recipient has joined ("join <code>" to +14155238886).
    #    Production senders are rejected with a 21654/21659 "use a template"
    #    error, which we retry below.
    try:
        message = client.messages.create(to=to_wa, from_=from_wa, body=body)
        _GATEWAY_STATE["whatsapp_sent"] += 1
        return {"ok": True, "sid": getattr(message, "sid", ""),
                "status": getattr(message, "status", "queued")}
    except Exception as exc:
        err = "{}: {}".format(type(exc).__name__, _clean_twilio_error(exc))
        if not _needs_template_retry(err):
            _GATEWAY_STATE["whatsapp_failed"] += 1
            return {"ok": False, "error": err}
        # 2) Retry path: sender required an approved template (21654 family).
        #    Try our own approved template SIDs first (production senders).
        content_sid = _template_for(body)
        if content_sid:
            try:
                message = client.messages.create(
                    to=to_wa, from_=from_wa, content_sid=content_sid,
                    content_variables=json.dumps({"1": body[:900]}),
                )
                _GATEWAY_STATE["whatsapp_sent"] += 1
                return {"ok": True, "sid": getattr(message, "sid", ""),
                        "status": getattr(message, "status", "queued"),
                        "via": "twilio-whatsapp-template", "content_sid": content_sid}
            except Exception as exc2:
                err2 = "{}: {}".format(type(exc2).__name__, _clean_twilio_error(exc2))
                # If our template send also needs a template (sandbox still
                # requires join), fall through to the sandbox-template path.
                if not _needs_template_retry(err2):
                    _GATEWAY_STATE["whatsapp_failed"] += 1
                    return {"ok": False, "error": err2,
                            "hint": "Production WhatsApp needs an approved template. Create one in Twilio Console > Messaging > Content Template Builder, approve for WhatsApp, set TWILIO_CONTENT_SID_GENERIC in backend/.env."}
        # 3) Sandbox sender (+14155238886): try Twilio's sandbox-approved
        #    templates via ContentSid (works once the phone joined the sandbox).
        if from_wa == "whatsapp:+14155238886":
            sb = _send_via_sandbox_template(client, to_wa, body, from_wa)
            if sb.get("ok"):
                return sb
            _GATEWAY_STATE["whatsapp_failed"] += 1
            return {"ok": False, "error": err,
                    "hint": "Sandbox requires an approved template and your phone must have joined it. Get the sandbox code + template SIDs from Twilio Console > Messaging > Try it out > WhatsApp > Sandbox, then set TWILIO_SANDBOX_CONTENT_SID in backend/.env. The sandbox code appears when you open that page; text 'join <code>' to +1 415 523 8886 once from your phone."}
        _GATEWAY_STATE["whatsapp_failed"] += 1
        return {"ok": False, "error": err,
                "hint": "Twilio demands an approved WhatsApp template (21654 family). Set TWILIO_CONTENT_SID_GENERIC (or OTP/SUBMITTED/SANCTIONED/SENTBACK SIDs) in backend/.env. Sandbox accepts free-form Body; production senders do not."}


def _persist_log(body: str, user_id: str, application_id: str, phone: str, status: str) -> None:
    try:
        db.execute(
            "INSERT INTO sms_outbox (id, user_id, application_id, phone, body, "
            "status, attempts, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (db.new_id("wmsg"), user_id or "", application_id or "", phone or "",
             body, status, 0, db._now()),
        )
    except Exception:
        pass



# Sandbox pre-approved templates (on trial accounts these are the only sends
# allowed outside the 24h customer-service window). They need the recipient's
# phone to have joined the sandbox. SIDs come from .env (set on the sandbox
# config page in the Twilio Console) — never hard-coded because they are
# account-specific.
_SANDBOX_SID_VARS = (
    # (config_var, template_name, num_variables)
    ("TWILIO_SANDBOX_CONTENT_SID", "generic", 4),
    ("TWILIO_CONTENT_SID_OTP", "otp", 2),
)


def _sandbox_template_sids() -> list:
    """Approved template SIDs configured in backend/.env for this sandbox."""
    sids = []
    for var in ("TWILIO_SANDBOX_CONTENT_SID", "TWILIO_CONTENT_SID_GENERIC",
                "TWILIO_CONTENT_SID_SUBMITTED", "TWILIO_CONTENT_SID_SANCTIONED",
                "TWILIO_CONTENT_SID_SENTBACK", "TWILIO_CONTENT_SID_OTP"):
        val = getattr(config, var, "") or ""
        if val and val not in sids:
            sids.append(val)
    return sids


def _sandbox_content_variables(body: str) -> dict:
    """Map an INDUS ROUTE message body onto a sandbox template's variables.

    The sandbox ships a small, fixed set of pre-approved templates whose
    variable layout cannot change. For status messages we fold the body into
    {{1}}; for OTP we split into {{1}}=brand and {{2}}=the code (matches the
    sandbox "Verification Codes" template: "Your {{1}} code is {{2}}").
    """
    upper = str(body or "").upper()
    if "OTP" in upper:
        # Split "INDUS ROUTE: ... OTP is 123456 ..." -> pull out the digits.
        import re as _re
        m = _re.search(r"(\d{4,8})", body or "")
        code = m.group(1) if m else ""
        return {"1": "INDUS ROUTE", "2": code, "3": "", "4": ""}
    return {"1": body[:320], "2": "", "3": "", "4": ""}


def _send_via_sandbox_template(client, to_wa: str, body: str, from_wa: str) -> dict:
    """Sandbox: send via a configured approved template (ContentSid)."""
    sids = _sandbox_template_sids()
    if not sids:
        return {"ok": False, "error": "no_sandbox_template_sid_configured"}
    variables = _sandbox_content_variables(body)
    for sid in sids:
        try:
            message = client.messages.create(
                to=to_wa, from_=from_wa, content_sid=sid,
                content_variables=json.dumps(variables),
            )
            _GATEWAY_STATE["whatsapp_sent"] += 1
            return {"ok": True, "sid": getattr(message, "sid", ""),
                    "status": getattr(message, "status", "queued"),
                    "via": "twilio-whatsapp-sandbox-template", "content_sid": sid}
        except Exception:
            continue
    return {"ok": False, "error": "all_sandbox_templates_invalid"}



def queue_whatsapp(body: str, user_id: str = "", application_id: str = "", phone: str = "") -> dict:
    """Send branded WhatsApp via Twilio. Never raises."""
    text = brand(body)[:1000]
    if not text:
        return {"status": "logged", "detail": "empty body - nothing queued"}
    to_wa = _resolve_recipient(phone, user_id)
    if not to_wa:
        _persist_log(text, user_id, application_id, phone or "", "logged-no-recipient")
        _GATEWAY_STATE["logged"] += 1
        return {"status": "logged", "detail": "no recipient phone known", "via": "log-only"}
    result = _send_via_twilio(to_wa, text)
    if result.get("ok"):
        _persist_log(text, user_id, application_id, to_wa, "sent")
        return {"status": "sent", "sid": result.get("sid"), "via": result.get("via", "twilio-whatsapp"),
                "to": to_wa, "from": _sender()}
    _persist_log(text + " [FAILED: {}]".format(result.get("error", "")[:200]),
                 user_id, application_id, to_wa, "failed")
    _GATEWAY_STATE["logged"] += 1
    out = {"status": "failed", "detail": result.get("error", "send failed"),
           "via": "twilio-whatsapp", "to": to_wa, "from": _sender()}
    if result.get("hint"):
        out["hint"] = result["hint"]
    logger.warning("WhatsApp send failed to %s: %s", to_wa, result.get("error", "")[:300])
    return out


def queue_sms(body: str, user_id: str = "", application_id: str = "", phone: str = "") -> dict:
    """Deprecated alias - everything is WhatsApp now."""
    return queue_whatsapp(body, user_id=user_id, application_id=application_id, phone=phone)


def send_test_otp(phone: str, otp: str = "123456") -> dict:
    """Send an OTP via branded WhatsApp (INDUS ROUTE).

    Uses the sandbox approved template (ContentSid) configured in .env.
    On a trial account without a configured ContentSid, returns a clear hint.
    """
    return queue_whatsapp(
        "Your OTP is {} . Valid 10 min. Never share this OTP.".format(otp),
        phone=phone,
    )
