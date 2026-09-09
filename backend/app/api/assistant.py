"""Real-time applicant assistant — 1:1 chat with persistent sessions.

Endpoints:
- POST /assistant/chat    — request/reply (non-streaming)
- POST /assistant/stream  — Server-Sent Events, token-by-token reply
- GET  /assistant/history — replay a session (owner-only, RBAC enforced)

The assistant is advisory-only: it reads the applicant's own live application
context (failed checks, missing docs, SLA, decisions) and explains it. It can
never decide an approval — matching the platform's "rules decide" contract.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..models.schemas import ChatRequest
from .deps import get_current_user, audit
from ..core import chat_engine

router = APIRouter(tags=["assistant"])


@router.post("/assistant/chat")
def assistant_chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    result = chat_engine.respond(user, body.message, body.session_id or "")
    audit("assistant", result["session_id"], user, "assistant_reply",
          "intent={}; mode={}".format(result["intent"],
                                      "gemini" if result["ai_generated"] else "deterministic"))
    return result


@router.post("/assistant/stream")
def assistant_stream(body: ChatRequest, user: dict = Depends(get_current_user)):
    return StreamingResponse(
        chat_engine.stream_reply(user, body.message, body.session_id or ""),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/assistant/history")
def assistant_history(session_id: str = "", user: dict = Depends(get_current_user)):
    return {"session_id": session_id,
            "messages": chat_engine.history(user, session_id or "")}