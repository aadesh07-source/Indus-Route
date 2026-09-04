"""Shared API dependencies: RBAC, audit helper, notification helper."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from .. import db
from ..security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


def _auth_error(detail: str, code: int = 401) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise _auth_error("Not authenticated. Provide a Bearer token.")
    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise _auth_error("Invalid or expired token: {}".format(exc))
    user = db.query_one("SELECT id, name, phone, email, role FROM users WHERE id=?",
                        (payload["sub"],))
    if user is None:
        raise _auth_error("Account no longer exists.", 403)
    return user


def require_roles(*roles: str):
    """Dependency factory enforcing RBAC at the API layer (doc 3.6)."""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires role: {} (you are '{}').".format(
                    " or ".join(roles), user["role"]),
            )
        return user
    return checker


def get_own_profile(user: dict) -> dict:
    profile = db.query_one("SELECT * FROM business_profiles WHERE owner_id=?",
                           (user["id"],))
    if profile is None:
        raise HTTPException(status_code=404,
                            detail="No business profile found. Create one first.")
    return profile


def load_profile_dict(profile_row: dict) -> dict:
    return {
        "id": profile_row["id"],
        "name": profile_row["name"],
        "sector": profile_row["sector"],
        "district": profile_row["district"],
        "industrial_zone": profile_row["industrial_zone"],
        "investment_size": profile_row["investment_size"],
        "employee_count": profile_row["employee_count"],
        "project_stage": profile_row["project_stage"],
        "pan_hash": profile_row["pan_hash"],
        "gst_hash": profile_row["gst_hash"],
    }


def audit(entity_type: str, entity_id: str, actor: dict, action: str,
          reasoning: str = "", meta: Optional[dict] = None) -> None:
    """Append an audit row. actor_id='system' for automated paths."""
    try:
        db.execute(
            "INSERT INTO audit_log (id, entity_type, entity_id, actor_id, actor_role, "
            "action, reasoning, decision_source, meta, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (db.new_id("log"), entity_type, entity_id,
             actor.get("id", "system"), actor.get("role", ""),
             action, reasoning, "human" if actor.get("id", "system") != "system" else "system",
             db.jdumps(meta or {}), db._now()),
        )
    except Exception:
        pass  # audit failures must never break the main flow (logged by SQLite trigger rules)


def notify(user_id: str, title: str, body: str, application_id: str = "",
           channel: str = "in_app", sms_body: str = "") -> None:
    from ..notifications.sms_gateway import queue_sms

    try:
        db.execute(
            "INSERT INTO notifications (id, user_id, application_id, channel, title, body, "
            "status, created_at) VALUES (?,?,?,?,?,?, 'sent', ?)",
            (db.new_id("ntf"), user_id, application_id or "", channel, title, body,
             db._now()),
        )
        if sms_body:
            queue_sms(sms_body, user_id=user_id, application_id=application_id)
    except Exception:
        pass
