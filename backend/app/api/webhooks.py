"""INDUS ROUTE webhooks: WhatsApp dispatch + Twilio status callbacks.

- POST /webhooks/whatsapp/send : authenticated manual WhatsApp send
  (used by the portal "test" button + ops tooling).
- GET  /webhooks/whatsapp/status : live gateway diagnostics for /health.
- POST /webhooks/twilio/status   : Twilio delivery-status callback target.
No PII in message bodies.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Request

from ..models.schemas import SmsDispatchRequest
from .. import config
from ..notifications.whatsapp_gateway import queue_whatsapp, gateway_status
from .deps import get_current_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_WEBHOOK_TOKEN = ""


def _check_token(provided: str) -> None:
    expected = _WEBHOOK_TOKEN or getattr(config, "TWILIO_AUTH_TOKEN", "")
    if expected and provided != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook token.")
    if expected and not provided:
        raise HTTPException(status_code=401, detail="Missing webhook token.")


@router.post("/whatsapp/send")
def whatsapp_send(body: SmsDispatchRequest,
                  user: dict = Depends(get_current_user)):
    from .. import db as _db
    phone = ""
    if body.user_id:
        urow = _db.query_one("SELECT phone FROM users WHERE id=?", (body.user_id,))
        phone = (urow.get("phone", "") if urow else "") or ""
    result = queue_whatsapp(body.message, user_id=body.user_id,
                            application_id=body.application_id, phone=phone)
    return {"dispatch": result, "gateway": gateway_status()}


# Backwards-compatible alias for older clients.
@router.post("/sms-dispatch")
def sms_dispatch_alias(body: SmsDispatchRequest,
                       user: dict = Depends(get_current_user)):
    return whatsapp_send(body, user)


@router.get("/whatsapp/status")
def whatsapp_status():
    return gateway_status()


@router.get("/sms/status")
def sms_status_alias():
    return gateway_status()


@router.post("/twilio/status")
async def twilio_status_callback(request: Request):
    """Twilio MessageStatusCallback target. Logs delivery updates; always 200."""
    try:
        form = await request.form()
        data = dict(form)
    except Exception:
        data = {}
    try:
        from .. import db as _db
        _db.execute(
            "INSERT INTO notifications (id, user_id, application_id, channel, title, body, "
            "status, created_at) VALUES (?,?,?,?,?,?, 'sent', ?)",
            (_db.new_id("ntf"), "", "", "whatsapp-callback",
             "Twilio status: {}".format(data.get("MessageStatus", "unknown")),
             "SID {} status {}".format(data.get("MessageSid", ""), data.get("MessageStatus", "")),
             _db._now()),
        )
    except Exception:
        pass
    return {"ok": True}

