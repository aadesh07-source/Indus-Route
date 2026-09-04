"""Authentication primitives: PBKDF2 password hashing and HS256 JWT.

Implemented with the Python standard library only (no PyJWT/jose), so the
auth layer can never fail due to a missing or incompatible dependency.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Optional

from . import config

_PBKDF2_ITERATIONS = 200_000
_SECRET = config.SECRET_KEY.encode("utf-8")


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return "pbkdf2${}${}${}".format(
        _PBKDF2_ITERATIONS, salt.hex(), digest.hex()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_hex, digest_hex = stored.split("$", 3)
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------- JWT (HS256)
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def create_token(user_id: str, role: str, expires_hours: Optional[int] = None) -> str:
    hours = expires_hours or config.TOKEN_EXPIRE_HOURS
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + hours * 3600,
    }
    signing_input = "{}.{}".format(
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(payload, separators=(",", ":")).encode()),
    )
    signature = hmac.new(_SECRET, signing_input.encode("ascii"), hashlib.sha256).digest()
    return "{}.{}".format(signing_input, _b64url(signature))


def decode_token(token: str) -> dict:
    """Return the payload or raise ValueError with a safe message."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".", 2)
        signing_input = "{}.{}".format(header_b64, payload_b64)
        expected = hmac.new(_SECRET, signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected), sig_b64):
            raise ValueError("invalid signature")
        payload = json.loads(_unb64url(payload_b64))
        if float(payload.get("exp", 0)) < time.time():
            raise ValueError("token expired")
        if not payload.get("sub") or not payload.get("role"):
            raise ValueError("malformed token")
        return payload
    except ValueError:
        raise
    except Exception:
        raise ValueError("malformed token")


def sha256_hex(value: str) -> str:
    """Stable hash used for PAN/GST references and declaration integrity."""
    return hashlib.sha256(value.strip().upper().encode("utf-8")).hexdigest()
