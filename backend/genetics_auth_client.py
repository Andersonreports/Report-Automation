"""
genetics_auth_client.py — talks to IT's external auth gateway
(integration.andrsn.in) for real username + password + OTP login.

Two layers of credentials are involved:
  1. A service account (GENETICS_API_USERNAME/PASSWORD) exchanged for a
     short-lived Bearer token via /auth/login. This authenticates *this
     server* to IT's gateway — it has nothing to do with the end user.
  2. The end user's own username/password + OTP, sent under that Bearer
     token via /genetics/login and /genetics/verify_otp.

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


def _post(path: str, body: dict) -> dict:
    if not is_configured():
        raise GeneticsApiError(
            "GENETICS_API_USERNAME / GENETICS_API_PASSWORD are not set in the backend .env file."
        )

    token = _get_service_token()
    try:
        resp = requests.post(
            f"{_BASE_URL}{path}",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 401:
            token = _get_service_token(force_refresh=True)
            resp = requests.post(
                f"{_BASE_URL}{path}",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
                timeout=_TIMEOUT,
            )
    except requests.RequestException as e:
        raise GeneticsApiError(f"Could not reach {path}: {e}")

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if not resp.ok:
        message = data.get("message") or data.get("error") or resp.text[:300] or "Request failed."
        raise GeneticsApiError(message)
    return data


def genetics_login(user_name: str, password: str) -> dict:
    """Validates the end user's credentials with IT's gateway. On success
    this also triggers an OTP to their registered mobile and returns the
    `hash` needed to verify it in the same response."""
    data = _post("/genetics/login", {"user_name": user_name, "password": password})
    # IT's docs didn't show a sample response body — tolerate the hash
    # being nested under a `data` key as well as top-level.
    if "hash" not in data and isinstance(data.get("data"), dict):
        return data["data"]
    return data


def verify_otp(otp: str, otp_hash: str, mobile: str) -> dict:
    return _post("/genetics/verify_otp", {"otp": otp, "hash": otp_hash, "mobile": mobile})
