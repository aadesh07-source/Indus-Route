"""Internal webhook: trigger SMS dispatch through the gateway client.

Protected by a shared token (X-Webhook-Token) when configured — the Termux
relay must never be an open endpoint (doc 3.5). No PII in message bodies.
"""
from fastapi import APIRouter, Depends, HTTPException, Header

from ..models.schemas import SmsDispatchRequest
from .. import config, db
from ..notifications.sms_gateway import queue_sms, gateway_status
from .deps import get_current_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/sms-dispatch")
def sms_dispatch(body: SmsDispatchRequest,
                 x_webhook_token: str = Header(default="")):
    if config.SMS_WEBHOOK_TOKEN and x_webhook_token != config.SMS_WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid webhook token.")
    if config.SMS_WEBHOOK_TOKEN and not x_webhook_token:
        raise HTTPException(status_code=401, detail="Missing webhook token.")
    result = queue_sms(body.message, user_id=body.user_id,
                       application_id=body.application_id)
    return {"dispatch": result, "gateway": gateway_status()}


@router.get("/sms/status")
def sms_status():
    return gateway_status()
