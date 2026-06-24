"""
genetics_auth_client.py — talks to IT's external auth gateway
(integration.andrsn.in) for real mobile number + password + OTP login.

Two layers of credentials are involved:
  1. A service account (GENETICS_API_USERNAME/PASSWORD) exchanged for a
     short-lived Bearer token via /auth/login. This authenticates *this
     server* to IT's gateway — it has nothing to do with the end user.
  2. The end user's own mobile number/password + OTP, sent under that
     Bearer token via /genetics/login and /genetics/verify_otp.

This module only proves "this person is who they say they are." Role and
per-report access (the Admin page) are layered on top of it in
access_api.py / mysql_client.py.
"""

import base64
import json
import os
import time

import requests

_BASE_URL = os.getenv("GENETICS_API_BASE", "https://integration.andrsn.in").rstrip("/")
_SERVICE_USERNAME = os.getenv("GENETICS_API_USERNAME", "")
_SERVICE_PASSWORD = os.getenv("GENETICS_API_PASSWORD", "")
_TIMEOUT = 10

_token = None
_token_expiry = 0.0


class GeneticsApiError(Exception):
    """Raised when IT's auth gateway rejects a request or can't be reached."""


def is_configured() -> bool:
    return bool(_SERVICE_USERNAME and _SERVICE_PASSWORD)


def _decode_jwt_exp(token: str):
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload["exp"])
    except Exception:
        return None


def _fetch_service_token() -> str:
    try:
        resp = requests.post(
            f"{_BASE_URL}/auth/login",
            json={"username": _SERVICE_USERNAME, "password": _SERVICE_PASSWORD},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        raise GeneticsApiError(f"Could not reach the auth service: {e}")

    if not resp.ok:
        raise GeneticsApiError(f"Service auth failed ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    token = data.get("token") or data.get("access_token") or (data.get("data") or {}).get("token")
    if not token:
        raise GeneticsApiError(
            f"Service auth response had no recognizable token field (keys: {list(data.keys())})."
        )
    return token


def _get_service_token(force_refresh: bool = False) -> str:
    global _token, _token_expiry
    if force_refresh or _token is None or time.time() >= _token_expiry:
        _token = _fetch_service_token()
        exp = _decode_jwt_exp(_token)
        # Leave a 30s safety margin before the token's real expiry; fall back
        # to a conservative 13 minutes if the token isn't a decodable JWT.
        _token_expiry = (exp - 30) if exp else (time.time() + 13 * 60)
    return _token


def _do_post(path: str, body: dict, token: str):
    resp = requests.post(
        f"{_BASE_URL}{path}",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=_TIMEOUT,
    )
    try:
        data = resp.json()
    except ValueError:
        data = {}
    return resp, data


def _post(path: str, body: dict) -> dict:
    if not is_configured():
        raise GeneticsApiError(
            "GENETICS_API_USERNAME / GENETICS_API_PASSWORD are not set in the backend .env file."
        )

    token = _get_service_token()
    try:
        resp, data = _do_post(path, body, token)
        
        if resp.status_code == 401 and data.get("message") != "success":
            token = _get_service_token(force_refresh=True)
            resp, data = _do_post(path, body, token)
    except requests.RequestException as e:
        raise GeneticsApiError(f"Could not reach {path}: {e}")

    ok = resp.ok or data.get("message") == "success"
    if not ok:
        message = data.get("message") or data.get("error") or resp.text[:300] or "Request failed."
        raise GeneticsApiError(message)
    return data


def genetics_login(user_name: str, password: str) -> dict:
    """Validates the end user's credentials with IT's gateway. On success
    this also triggers an OTP to their registered mobile. IT's response
    shape is `{"message": "success", "data": "<hash>"}` — the hash needed
    for verify_otp is the `data` field itself, not a nested `hash` key."""
    data = _post("/genetics/login", {"user_name": user_name, "password": password})
    otp_hash = data.get("hash")
    if not otp_hash:
        nested = data.get("data")
        if isinstance(nested, str):
            otp_hash = nested
        elif isinstance(nested, dict):
            otp_hash = nested.get("hash")
    return {"hash": otp_hash}


def verify_otp(otp: str, otp_hash: str, mobile: str) -> dict:
    return _post("/genetics/verify_otp", {"otp": otp, "hash": otp_hash, "mobile": mobile})


def get_patient_details(from_date: str, to_date: str, reporting_type: str) -> list:
    data = _post("/genetics/get_patient_details", {
        "from_date": from_date,
        "to_date": to_date,
        "reporting_type": reporting_type,
    })
    return data.get("data") or []
