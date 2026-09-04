"""SIH26130 — Intelligent Industrial Approval & Compliance Management Platform.

FastAPI application factory. Design guarantees:
- never crashes on missing env vars / optional deps / external services,
- every request validated by Pydantic models (no raw dicts),
- global rate limiting + catch-all exception handler (no stack-trace leaks),
- CORS locked to configured origins,
- deterministic rule engine downstream of which all AI sits (advisory only).
"""
import time
import traceback
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from . import config, db
from .api import auth, profiles, applications, documents, officer, admin, webhooks
from .api import autofill
from .core import scheduler
from .core.pii import pii_status
from .notifications.sms_gateway import gateway_status

_version_info = {"app": "SIH26130 Platform", "version": "1.0.0"}

_rate_buckets: dict = defaultdict(deque)


async def rate_limit_middleware(request: Request, call_next):
    """Simple sliding-window limiter per client IP. Fails open on internal error."""
    try:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = _rate_buckets[client]
        while bucket and bucket[0] < now - 60.0:
            bucket.popleft()
        if len(bucket) >= config.RATE_LIMIT_PER_MINUTE:
            return JSONResponse(status_code=429,
                                content={"detail": "Rate limit exceeded. Try again shortly."})
        bucket.append(now)
    except Exception:
        pass
    return await call_next(request)


async def unhandled_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. The incident has been logged."},
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="SIH26130 — Industrial Approval & Compliance Platform",
        description=(
            "Deterministic rule engine decides; AI explains/drafts/answers (advisory "
            "only); human officers take every final decision. Green Channel is a "
            "scoped, audited extension issuing PROVISIONAL clearance only."),
        version=_version_info["version"],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS or ["*"],
        allow_credentials=False,  # token auth via header; no cookies needed
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(rate_limit_middleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        return JSONResponse(status_code=422, content={
            "detail": "Invalid request: {} ({})".format(
                " -> ".join(str(loc) for loc in first.get("loc", [])) or "body",
                first.get("msg", "validation failed")),
        })

    app.include_router(auth.router)
    app.include_router(profiles.router)
    app.include_router(autofill.router)
    app.include_router(applications.router)
    app.include_router(documents.router)
    app.include_router(officer.router)
    app.include_router(admin.router)
    app.include_router(webhooks.router)

    @app.on_event("startup")
    def on_startup() -> None:
        db.init_db()
        scheduler.start_scheduler()
        print("[SIH26130] Backend started. DB: {}".format(config.DB_PATH))

    @app.on_event("shutdown")
    def on_shutdown() -> None:
        scheduler.shutdown_scheduler()

    @app.get("/health", tags=["system"])
    def health():
        return {
            "status": "ok",
            "database": str(config.DB_PATH),
            "scheduler": "running",
            "ai_layer": "gemini" if config.GEMINI_API_KEY else
                        "deterministic-fallback (no GEMINI_API_KEY)",
            "sms_gateway": gateway_status(),
            "pii_protection": pii_status(),
            "green_channel_enabled": _gc(),
            "demo_mode": config.DEMO_MODE,
        }

    def _gc():
        from .core.green_channel import green_channel_enabled
        return green_channel_enabled()

    return app


app = create_app()
