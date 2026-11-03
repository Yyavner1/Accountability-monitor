"""Authentication: password hashing, API keys, and session cookies."""

from __future__ import annotations

import hashlib
import secrets

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext
from sqlmodel import Session, select

from .config import settings
from .db import get_session
from .models import Device, User

_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
_signer = URLSafeSerializer(settings.secret_key, salt="session")

SESSION_COOKIE = "am_session"


# --- single-use tokens (verification, password reset) ----------------------

from itsdangerous import URLSafeTimedSerializer  # noqa: E402

_verify_ts = URLSafeTimedSerializer(settings.secret_key, salt="verify")
_reset_ts = URLSafeTimedSerializer(settings.secret_key, salt="reset")


def make_verify_token(user_id: int) -> str:
    return _verify_ts.dumps({"uid": user_id})


def read_verify_token(token: str, max_age: int = 7 * 24 * 3600) -> int | None:
    try:
        return int(_verify_ts.loads(token, max_age=max_age)["uid"])
    except Exception:
        return None


def make_reset_token(user_id: int) -> str:
    return _reset_ts.dumps({"uid": user_id})


def read_reset_token(token: str, max_age: int = 3600) -> int | None:
    try:
        return int(_reset_ts.loads(token, max_age=max_age)["uid"])
    except Exception:
        return None


# --- passwords -------------------------------------------------------------

def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd.verify(password, hashed)


# --- device API keys -------------------------------------------------------

def new_api_key() -> str:
    return "am_" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    # Fast deterministic hash so we can look the device up by it; the key has
    # 256 bits of entropy, so a plain SHA-256 is appropriate here.
    return hashlib.sha256(key.encode()).hexdigest()


def device_from_api_key(key: str, session: Session) -> Device | None:
    hashed = hash_api_key(key)
    return session.exec(
        select(Device).where(Device.api_key_hash == hashed)
    ).first()


# --- session cookies -------------------------------------------------------

def make_session_cookie(user_id: int) -> str:
    return _signer.dumps({"uid": user_id})


def read_session_cookie(value: str) -> int | None:
    try:
        data = _signer.loads(value)
        return int(data["uid"])
    except (BadSignature, KeyError, ValueError, TypeError):
        return None


# --- login rate limiting (in-memory) ---------------------------------------

import time as _time  # noqa: E402

_attempts: dict[str, list[float]] = {}
_WINDOW = 300.0   # seconds
_MAX_TRIES = 8    # per window per key


def too_many_attempts(key: str) -> bool:
    now = _time.time()
    tries = [t for t in _attempts.get(key, []) if now - t < _WINDOW]
    _attempts[key] = tries
    return len(tries) >= _MAX_TRIES


def record_attempt(key: str) -> None:
    _attempts.setdefault(key, []).append(_time.time())


def clear_attempts(key: str) -> None:
    _attempts.pop(key, None)


def current_user(
    request: Request, session: Session = Depends(get_session)
) -> User:
    raw = request.cookies.get(SESSION_COOKIE)
    uid = read_session_cookie(raw) if raw else None
    user = session.get(User, uid) if uid else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in"
        )
    return user
