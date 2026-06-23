"""
access_api.py — User login + admin CRUD for the per-report access control
system (Admin page + "Access Denied" guards on each report app).

Identity (username + password + OTP) is verified by IT's genetics auth
gateway via genetics_auth_client.py. mysql_client.py's `users` table no
longer checks a local password — it's only used to look up the role and
single report an already-verified username is allowed to see. Until
MYSQL_HOST/USER/PASSWORD/DATABASE are set in the .env file,
mysql_client.mysql_enabled is False and every CRUD route here returns a
clear 503; login instead falls back to unrestricted access (matching
pre-access-control behavior) since there's no local table to consult.
"""

from fastapi import APIRouter, HTTPException

import genetics_auth_client as genetics
import mysql_client as db

router = APIRouter(prefix="/access", tags=["access"])

REPORT_KEYS = db.USER_REPORT_KEYS

_NOT_CONFIGURED_MSG = (
    "MySQL is not configured yet. Set MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, "
    "and MYSQL_DATABASE in the backend .env file, then restart the server."
)


def _require_mysql():
    if not db.mysql_enabled:
        raise HTTPException(503, _NOT_CONFIGURED_MSG)


@router.post("/login")
async def login(body: dict):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        raise HTTPException(400, "Username and password are required.")

    try:
        result = genetics.genetics_login(username, password)
    except genetics.GeneticsApiError as e:
        raise HTTPException(401, str(e))

    otp_hash = result.get("hash")
    if not otp_hash:
        raise HTTPException(502, "Login succeeded but the auth service returned no OTP hash.")

    return {"otp_required": True, "mobile": username, "hash": otp_hash}


@router.post("/verify-otp")
async def verify_otp(body: dict):
    otp = (body.get("otp") or "").strip()
    otp_hash = body.get("hash") or ""
    mobile = (body.get("mobile") or "").strip()
    if not otp or not otp_hash or not mobile:
        raise HTTPException(400, "otp, hash, and mobile are required.")

    try:
        genetics.verify_otp(otp, otp_hash, mobile)
    except genetics.GeneticsApiError as e:
        raise HTTPException(401, str(e))

    if not db.mysql_enabled:
        # No local table to look up role/report — fail open, same as the
        # rest of this module does while MySQL isn't configured.
        return {"username": mobile, "role": "user", "report": None, "access_control": False}

    user = db.get_user_by_username(mobile)
    if not user:
        raise HTTPException(
            403, "Your account isn't set up for any report yet. Contact an administrator."
        )
    return user


@router.get("/users")
async def list_users():
    _require_mysql()
    return {"users": db.list_users(), "report_keys": REPORT_KEYS}


@router.post("/users")
async def create_user(body: dict):
    _require_mysql()
    username = (body.get("username") or "").strip()
    role = body.get("role") or "user"
    report = body.get("report") or None

    if not username:
        raise HTTPException(400, "Username is required.")
    if role not in ("admin", "user"):
        raise HTTPException(400, "Role must be 'admin' or 'user'.")
    if role == "user" and report not in REPORT_KEYS:
        raise HTTPException(400, f"report must be one of {REPORT_KEYS} for a non-admin user.")

    try:
        return db.create_user(username, role, report)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: dict):
    _require_mysql()
    fields = {}
    if "username" in body and body["username"].strip():
        fields["username"] = body["username"].strip()
    if "password" in body and body["password"]:
        fields["password"] = body["password"]
    if "role" in body:
        if body["role"] not in ("admin", "user"):
            raise HTTPException(400, "Role must be 'admin' or 'user'.")
        fields["role"] = body["role"]
    if "report" in body:
        fields["report"] = body["report"] or None

    effective_role = fields.get("role")
    effective_report = fields.get("report")
    if effective_role == "user" and "report" in fields and effective_report not in REPORT_KEYS:
        raise HTTPException(400, f"report must be one of {REPORT_KEYS} for a non-admin user.")

    try:
        return db.update_user(user_id, **fields)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    _require_mysql()
    try:
        db.delete_user(user_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
