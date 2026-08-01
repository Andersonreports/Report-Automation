
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

def _logged_in_user(mobile: str) -> dict:
    if not db.mysql_enabled:
        return {"mobile_number": mobile, "role": "user", "report": None, "access_control": False}

    user = db.get_user_by_mobile_number(mobile)
    if not user:
        raise HTTPException(
            403, "Your account isn't set up for any report yet. Contact an administrator."
        )
    return user


@router.post("/login")
async def login(body: dict):
    mobile = (body.get("mobile") or "").strip()
    password = body.get("password") or ""
    if not mobile or not password:
        raise HTTPException(400, "Mobile number and password are required.")

    try:
        result = genetics.genetics_login(mobile, password)
        print(result)
    except genetics.GeneticsApiError as e:
        raise HTTPException(401, str(e))

    otp_hash = result.get("hash")
    if not otp_hash:
        if result.get("success") is True and result.get("message") == "Login successful":
            return {**_logged_in_user(mobile), "otp_required": False}
        raise HTTPException(502, "Login succeeded but the auth service returned no OTP hash.")

    return {"otp_required": True, "mobile": mobile, "hash": otp_hash}

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

    return _logged_in_user(mobile)


@router.post("/patients")
async def get_patients(body: dict):
    from_date = (body.get("from_date") or "").strip()
    to_date = (body.get("to_date") or "").strip()
    reporting_type = (body.get("reporting_type") or "").strip()
    if not from_date or not to_date or not reporting_type:
        raise HTTPException(400, "from_date, to_date, and reporting_type are required.")

    try:
        patients = genetics.get_patient_details(
            f"{from_date} 00:00:00", f"{to_date} 23:59:59", reporting_type
        )
    except genetics.GeneticsApiError as e:
        raise HTTPException(502, str(e))
    return {"patients": patients}


@router.get("/users")
async def list_users():
    _require_mysql()
    return {"users": db.list_users(), "report_keys": REPORT_KEYS}


@router.post("/users")
async def create_user(body: dict):
    _require_mysql()
    mobile_number = (body.get("mobile") or "").strip()
    name = (body.get("name") or "").strip() or None
    role = body.get("role") or "user"
    report = body.get("report") or None

    if not mobile_number:
        raise HTTPException(400, "Mobile number is required.")
    if role not in ("admin", "user"):
        raise HTTPException(400, "Role must be 'admin' or 'user'.")
    if role == "user" and report not in REPORT_KEYS:
        raise HTTPException(400, f"report must be one of {REPORT_KEYS} for a non-admin user.")

    try:
        return db.create_user(mobile_number, role, report, name=name)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: dict):
    _require_mysql()
    fields = {}
    if "mobile" in body and body["mobile"].strip():
        fields["mobile_number"] = body["mobile"].strip()
    if "name" in body:
        fields["name"] = (body["name"] or "").strip() or None
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
