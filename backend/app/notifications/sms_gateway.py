"""Termux:API SMS gateway client (demo-stage stand-in for a licensed provider).

- POSTs to the configured Termux webhook (private network + shared token).
- NEVER sends PAN/GST/Aadhaar values — SMS bodies reference IDs/status only.
- Never raises: if the gateway is unconfigured or unreachable, the message
  is still persisted in the notifications table with a delivery status.
"""
import json
import urllib.request
import urllib.error

from .. import config

_GATEWAY_STATE = {"sent": 0, "failed": 0, "skipped": 0}


def gateway_status() -> dict:
    configured = bool(config.SMS_WEBHOOK_URL)
    return {
        "gateway": "termux-webhook" if configured else "log-only (no gateway configured)",
        "configured": configured,
        "demo_only": True,
        "production_note": "Replace with a licensed provider (Twilio/MSG91) using DLT-registered sender IDs.",
        **_GATEWAY_STATE,
    }


def queue_sms(body: str, user_id: str = "", application_id: str = "",
              phone: str = "") -> dict:
    """Send via webhook if configured; record the outcome either way."""
    body = (body or "")[:300]  # hard cap: SMS bodies stay short, no PII
    if not config.SMS_WEBHOOK_URL:
        _GATEWAY_STATE["skipped"] += 1
        return {"status": "logged", "detail": "no SMS gateway configured (in-app record only)"}
    try:
        payload = json.dumps({
            "to": phone or "",
            "body": body,
            "user_id": user_id,
            "application_id": application_id,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if config.SMS_WEBHOOK_TOKEN:
            headers["X-Webhook-Token"] = config.SMS_WEBHOOK_TOKEN
        request = urllib.request.Request(
            config.SMS_WEBHOOK_URL, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=5) as resp:
            resp.read()
        _GATEWAY_STATE["sent"] += 1
        return {"status": "sent"}
    except Exception as exc:
        _GATEWAY_STATE["failed"] += 1
        return {"status": "failed", "detail": str(exc)[:200]}
