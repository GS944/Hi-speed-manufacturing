"""JWT authentication: standard sign-up and sign-in.

Credentials are whatever people choose - no format rules. Accounts are protected instead by:
bcrypt hashing, a per-account lockout after repeated failures, per-IP rate limiting, signed expiring tokens,
and instant revocation (every token carries the account's token_version, bumped on password change/sign-out-all).
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .db import SessionLocal, User, get_db, get_setting, set_setting, utcnow

bearer = HTTPBearer(auto_error=False)

LOCK_AFTER = 5                         # failed passwords before an account is locked
LOCK_MINUTES = (1, 5, 15, 60)          # escalating lock duration for repeated lockouts


# ----------------------------------------------------------------------------- passwords
def _prepare(pw: str) -> bytes:
    raw = pw.encode("utf-8")
    # bcrypt only reads 72 bytes: longer passwords are pre-hashed so every character counts
    return base64.b64encode(hashlib.sha256(raw).digest()) if len(raw) > 72 else raw


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(_prepare(pw), bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(pw), hashed.encode())
    except ValueError:
        return False


# ----------------------------------------------------------------------------- tokens
_secret_lock = threading.Lock()
_secret: str | None = None


def jwt_secret() -> str:
    """JWT_SECRET from the environment, or a random secret generated once and kept in the database
    (so sessions survive restarts even on hosts without a persistent disk)."""
    global _secret
    if config.JWT_SECRET:
        return config.JWT_SECRET
    with _secret_lock:
        if _secret is None:
            with SessionLocal() as db:
                value = get_setting(db, "jwt_secret")
                if not value:
                    value = secrets.token_urlsafe(64)
                    set_setting(db, "jwt_secret", value)
                _secret = value
        return _secret


def create_token(user: User) -> tuple[str, datetime]:
    exp = datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRE_HOURS)
    payload = {"sub": str(user.id), "name": user.username, "role": user.role, "ver": user.token_version,
               "iat": int(time.time()), "exp": exp}
    return jwt.encode(payload, jwt_secret(), algorithm=config.JWT_ALGORITHM), exp


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=[config.JWT_ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token.")


def _user_from_token(token: str, db: Session) -> User:
    claims = decode_token(token)
    user = db.get(User, int(claims["sub"])) if str(claims.get("sub", "")).isdigit() else None
    if not user or user.token_version != claims.get("ver") or user.role != "admin":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is no longer valid. Please sign in again.")
    return user


def require_admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    token = creds.credentials if creds else None
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.",
                            headers={"WWW-Authenticate": "Bearer"})
    return _user_from_token(token, db)


# ----------------------------------------------------------------------------- brute-force protection
_attempts: dict[str, deque] = defaultdict(deque)
WINDOW_S, MAX_ATTEMPTS = 300, 20        # per client IP, across all accounts


def check_rate(ip: str) -> None:
    q = _attempts[ip]
    now = time.time()
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= MAX_ATTEMPTS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many sign-in attempts. Try again in a few minutes.")


def record_failure(ip: str) -> None:
    _attempts[ip].append(time.time())


def check_locked(user: User) -> None:
    if user.locked_until and user.locked_until > utcnow():
        mins = max(1, int((user.locked_until - utcnow()).total_seconds() // 60) + 1)
        raise HTTPException(status.HTTP_423_LOCKED,
                            f"This account is locked after repeated wrong passwords. Try again in {mins} minute{'s' if mins > 1 else ''}.")


def register_failed_login(db: Session, user: User) -> None:
    user.failed_logins = (user.failed_logins or 0) + 1
    if user.failed_logins % LOCK_AFTER == 0:
        level = min(user.failed_logins // LOCK_AFTER - 1, len(LOCK_MINUTES) - 1)
        user.locked_until = utcnow() + timedelta(minutes=LOCK_MINUTES[level])
    db.commit()


def register_good_login(user: User) -> None:
    user.failed_logins = 0
    user.locked_until = None
    user.last_login = utcnow()


# ----------------------------------------------------------------------------- accounts
def admin_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0)


def normalise_username(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "Please enter a username.")
    if len(name) > 80:
        raise HTTPException(400, "Usernames can be at most 80 characters.")
    return name


def check_password(pw: str) -> str:
    if not pw:
        raise HTTPException(400, "Please enter a password.")
    if len(pw) > 1000:
        raise HTTPException(400, "Passwords can be at most 1000 characters.")
    return pw


def signup_allowed(db: Session) -> bool:
    """Sign-up is always possible while no account exists, so a fresh installation can never be locked."""
    if admin_count(db) == 0:
        return True
    value = get_setting(db, "allow_signup")
    return config.ALLOW_SIGNUP if value is None else bool(value)


def ensure_admin_user() -> None:
    """Optional bootstrap from ADMIN_USERNAME / ADMIN_PASSWORD when no account exists yet."""
    if not (config.ADMIN_USERNAME and config.ADMIN_PASSWORD):
        return
    with SessionLocal() as db:
        if admin_count(db) == 0:
            db.add(User(username=config.ADMIN_USERNAME, password_hash=hash_password(config.ADMIN_PASSWORD), role="admin"))
            db.commit()
