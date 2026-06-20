"""
access_api.py — User login + admin CRUD for the interim per-report access
control system (Admin page + "Access Denied" guards on each report app).

Backed by mysql_client.py's `users` table. Until MYSQL_HOST/USER/PASSWORD/
DATABASE are set in the .env file, mysql_client.mysql_enabled is False and
every route here returns a clear 503 instead of crashing — the Admin page
shows that message until MySQL access is configured.

SECURITY NOTE: this is an interim scaffold (plain-text passwords, no
session/token validation) standing in for the IT team's real username +
password + OTP system. Do not treat it as production-grade auth.
"""

from fastapi import APIRouter, HTTPException

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
    _require_mysql()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        raise HTTPException(400, "Username and password are required.")

    user = db.get_user_by_credentials(username, password)
    if not user:
        raise HTTPException(401, "Invalid username or password.")
    return user


@router.get("/users")
async def list_users():
    _require_mysql()
    return {"users": db.list_users(), "report_keys": REPORT_KEYS}


@router.post("/users")
async def create_user(body: dict):
    _require_mysql()
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role") or "user"
    report = body.get("report") or None

    if not username or not password:
        raise HTTPException(400, "Username and password are required.")
    if role not in ("admin", "user"):
        raise HTTPException(400, "Role must be 'admin' or 'user'.")
    if role == "user" and report not in REPORT_KEYS:
        raise HTTPException(400, f"report must be one of {REPORT_KEYS} for a non-admin user.")

    try:
        return db.create_user(username, password, role, report)
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
