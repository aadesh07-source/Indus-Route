"""PII protection helpers (PAN/GST): encrypt-at-rest, hash, mask.

Uses Fernet (cryptography package, AES-128-CBC + HMAC) when available, with
an application-level key derived from SECRET_KEY. If the package is absent,
the system degrades gracefully: only the SHA-256 reference hash and a masked
display form are stored — the raw value is never persisted either way.
Raw Aadhaar numbers are NEVER stored anywhere in the platform (doc 3.1).
"""
import base64
import hashlib
import hmac
import os
from typing import Optional

from .. import config

try:
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore
    _KEY = base64.urlsafe_b64encode(
        hashlib.sha256(("pii:" + config.SECRET_KEY).encode()).digest())
    _fernet = Fernet(_KEY)
    _CRYPTO_OK = True
except ImportError:
    _fernet = None
    _CRYPTO_OK = False


def mask_value(value: str) -> str:
    """XXXXX1234F style masking (first 5 / last 4 visible)."""
    value = (value or "").strip().upper()
    if len(value) <= 9:
        return "*" * len(value)
    return value[:0] + "*" * (len(value) - 4) + value[-4:]


def encrypt_value(value: str) -> str:
    if not value:
        return ""
    if _CRYPTO_OK:
        try:
            return _fernet.encrypt(value.encode()).decode()
        except Exception:
            return ""
    return ""  # degraded mode: hash-only storage


def decrypt_value(token: str) -> Optional[str]:
    if not token:
        return None
    if _CRYPTO_OK:
        try:
            return _fernet.decrypt(token.encode()).decode()
        except (InvalidToken, Exception):
            return None
    return None


def reference_hash(value: str) -> str:
    """Deterministic hash used for cross-checks (uppercase-normalised)."""
    return hashlib.sha256((value or "").strip().upper().encode()).hexdigest()


def pii_status() -> dict:
    return {
        "encryption": "fernet-aes (cryptography pkg)" if _CRYPTO_OK
                      else "hash-only degraded mode (install 'cryptography')",
        "aadhaar_storage": "never stored (hash reference + OTP status only)",
        "masking": "display-masked for all roles; full value only via owner decrypt endpoint",
    }
