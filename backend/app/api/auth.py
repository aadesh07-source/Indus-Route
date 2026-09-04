"""Auth endpoints: role-scoped register/login, stronger auth for officials."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from ..models.schemas import RegisterRequest, LoginRequest
from .. import db
from ..security import hash_password, verify_password, create_token
from .deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(body: RegisterRequest):
    # Officers/admins require the org invite code (doc 3.6: stronger auth).
    if body.role in ("officer", "admin"):
        if (body.invite_code or "") != db_query_invite_code():
            raise HTTPException(
                status_code=403,
                detail="A valid department invite code is required for officer/admin registration.",
            )
    pw_hash = hash_password(body.password)
    uid = db.new_id("usr")
    try:
        db.execute(
            "INSERT INTO users (id, name, phone, email, password_hash, role, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, body.name.strip(), body.phone,
             (body.email or "").strip().lower() or None, pw_hash, body.role, db._now()),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409,
                            detail="A user with this phone/email already exists.")
    token = create_token(uid, body.role)
    from .deps import audit
    audit("user", uid, {"id": uid, "role": body.role}, "register",
          "Role-scoped registration.")
    return {"token": token, "user": {"id": uid, "name": body.name,
                                     "phone": body.phone, "role": body.role}}


def db_query_invite_code() -> str:
    from .. import config
    return config.ADMIN_INVITE_CODE


@router.post("/login")
def login(body: LoginRequest):
    identifier = body.identifier.strip().lower()
    user = db.query_one(
        "SELECT * FROM users WHERE lower(phone)=? OR lower(email)=?",
        (identifier, identifier),
    )
    if user is None or not verify_password(body.password, user["password_hash"]):
        # Same message for unknown user and wrong password (no user enumeration).
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    token = create_token(user["id"], user["role"])
    return {"token": token, "user": {"id": user["id"], "name": user["name"],
                                     "phone": user["phone"], "email": user["email"],
                                     "role": user["role"]}}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {"user": user}
