"""Environment-driven configuration with safe defaults.

Nothing in this module raises: every setting falls back to a working
default so the service never crashes on a missing environment variable.
"""
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    """Load backend/.env if present (KEY=VALUE lines, # comments).

    Never raises; real environment variables always take precedence.
    """
    try:
        env_file = BACKEND_ROOT / ".env"
        if not env_file.exists():
            return
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
    except Exception:
        pass


_load_dotenv()


def _env(key: str, default=None, cast=str):
    """Read an env var; on absence or cast failure return the default."""
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    if cast is str:
        return raw
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# --- Core ---
SECRET_KEY: str = _env("SIH_SECRET_KEY", "sih26130-dev-secret-change-in-production")
TOKEN_EXPIRE_HOURS: int = _env("SIH_TOKEN_EXPIRE_HOURS", 12, int)
ADMIN_INVITE_CODE: str = _env("SIH_ADMIN_INVITE_CODE", "MAHARASHTRA-2026")
DEMO_MODE: bool = _env_bool("SIH_DEMO_MODE", True)

# --- Data / uploads ---
DATA_DIR: Path = Path(_env("SIH_DATA_DIR", BACKEND_ROOT / "data"))
UPLOAD_DIR: Path = DATA_DIR / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB: int = _env("SIH_MAX_UPLOAD_MB", 10, int)
DB_PATH: Path = Path(_env("SIH_DB_PATH", DATA_DIR / "sih.db"))

# --- Green Channel (extension; admin toggle also stored in DB) ---
GREEN_CHANNEL_ENABLED: bool = _env_bool("SIH_GREEN_CHANNEL_ENABLED", True)
GC_RATE_LIMIT_PER_DAY: int = _env("SIH_GC_RATE_LIMIT_PER_DAY", 3, int)

# --- AI layer (optional) ---
GEMINI_API_KEY: str = _env("GEMINI_API_KEY", "")
GEMINI_MODEL: str = _env("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_TIMEOUT_SECONDS: int = _env("GEMINI_TIMEOUT_SECONDS", 15, int)

# --- SMS gateway (optional) ---
SMS_WEBHOOK_URL: str = _env("SIH_SMS_WEBHOOK_URL", "")
SMS_WEBHOOK_TOKEN: str = _env("SIH_SMS_WEBHOOK_TOKEN", "")

# --- CORS ---
CORS_ORIGINS: list = [
    o.strip() for o in _env(
        "SIH_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",") if o.strip()
]

# --- Rate limiting (simple in-memory sliding window) ---
RATE_LIMIT_PER_MINUTE: int = _env("SIH_RATE_LIMIT_PER_MINUTE", 240, int)
