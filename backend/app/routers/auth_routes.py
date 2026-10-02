"""Standard sign-up and sign-in, own-account changes and user management."""
from __future__ import annotations

import secrets
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth
from ..db import AuditLog, User, get_db, set_setting

router = APIRouter(prefix="/api", tags=["auth"])
_signup_lock = threading.Lock()
_DUMMY_HASH = auth.hash_password(secrets.token_hex(8))      # equalises timing for unknown usernames


class LoginIn(BaseModel):
    username: str
    password: str


class SignupIn(BaseModel):
    username: str
    password: str


class AccountIn(BaseModel):
    current_password: str
    new_username: str | None = None
    new_password: str | None = None


class NewUserIn(BaseModel):
    username: str
    password: str


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _user_json(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None}


def _find(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))


def _session(user: User) -> dict:
    token, exp = auth.create_token(user)
    return {"access_token": token, "token_type": "bearer", "expires_at": exp.isoformat(), "user": _user_json(user)}


# ----------------------------------------------------------------------------- sign up
@router.get("/auth/signup-status")
def signup_status(db: Session = Depends(get_db)):
    return {"allowed": auth.signup_allowed(db), "first_account": auth.admin_count(db) == 0}


@router.post("/auth/signup")
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)):
    """Create an account with any username and password, then sign in with it."""
    ip = _ip(request)
    auth.check_rate(ip)
    with _signup_lock:
        if not auth.signup_allowed(db):
            raise HTTPException(403, "New sign-ups are turned off. Ask an existing user to create an account for you.")
        name = auth.normalise_username(body.username)
        if _find(db, name):
            auth.record_failure(ip)
            raise HTTPException(409, f"The username “{name}” is already taken. Choose another, or sign in.")
        user = User(username=name, password_hash=auth.hash_password(auth.check_password(body.password)), role="admin")
        auth.register_good_login(user)
        db.add(user)
        db.add(AuditLog(username=name, action="signup", detail={"ip": ip}))
        db.commit()
    return _session(user)


class SignupSettingIn(BaseModel):
    allowed: bool


@router.put("/auth/signup-setting")
def set_signup(body: SignupSettingIn, user: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    set_setting(db, "allow_signup", body.allowed)
    db.add(AuditLog(username=user.username, action="allow_signup" if body.allowed else "disable_signup"))
    db.commit()
    return {"allowed": body.allowed}


# ----------------------------------------------------------------------------- sign in / out
@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = _ip(request)
    auth.check_rate(ip)
    if not body.username.strip() or not body.password:
        raise HTTPException(400, "Enter your username and password.")
    user = _find(db, body.username)
    if user:
        auth.check_locked(user)
    if not user or user.role != "admin":
        auth.verify_password(body.password, _DUMMY_HASH)
        auth.record_failure(ip)
        raise HTTPException(401, "Invalid username or password.")
    if not auth.verify_password(body.password, user.password_hash):
        auth.record_failure(ip)
        auth.register_failed_login(db, user)
        db.add(AuditLog(username=user.username, action="login_failed", detail={"ip": ip}))
        db.commit()
        raise HTTPException(401, "Invalid username or password.")
    auth.register_good_login(user)
    db.add(AuditLog(username=user.username, action="login", detail={"ip": ip}))
    db.commit()
    return _session(user)


@router.get("/auth/me")
def me(user: User = Depends(auth.require_admin)):
    return _user_json(user)


@router.post("/auth/logout")
def logout(everywhere: bool = False, user: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user.id)
    if everywhere:
        u.token_version += 1          # invalidates every token issued to this account
    db.add(AuditLog(username=u.username, action="logout_everywhere" if everywhere else "logout"))
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------- own account
@router.put("/auth/account")
def update_account(body: AccountIn, user: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Change your own username and/or password (current password required)."""
    u = db.get(User, user.id)
    if not auth.verify_password(body.current_password, u.password_hash):
        raise HTTPException(400, "Your current password is not correct.")
    changed = []
    if body.new_username is not None and body.new_username.strip() != u.username:
        name = auth.normalise_username(body.new_username)
        other = _find(db, name)
        if other and other.id != u.id:
            raise HTTPException(409, f"The username “{name}” is already taken.")
        u.username = name
        changed.append("username")
    if body.new_password:
        u.password_hash = auth.hash_password(auth.check_password(body.new_password))
        u.token_version += 1          # signs out every other session
        changed.append("password")
    if not changed:
        raise HTTPException(400, "Nothing to change.")
    db.add(AuditLog(username=u.username, action="update_account", detail={"changed": changed}))
    db.commit()
    return _session(u)


# ----------------------------------------------------------------------------- administrators
@router.get("/users")
def list_users(_: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    return {"signup_allowed": auth.signup_allowed(db),
            "users": [_user_json(u) for u in db.scalars(select(User).order_by(User.created_at))]}


@router.post("/users")
def create_user(body: NewUserIn, user: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    name = auth.normalise_username(body.username)
    if _find(db, name):
        raise HTTPException(409, f"The username “{name}” is already taken.")
    u = User(username=name, password_hash=auth.hash_password(auth.check_password(body.password)), role="admin")
    db.add(u)
    db.add(AuditLog(username=user.username, action="create_admin", detail={"new_user": name}))
    db.commit()
    return _user_json(u)


@router.delete("/users/{user_id}")
def delete_user(user_id: int, user: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found.")
    if u.id == user.id:
        raise HTTPException(400, "You cannot remove your own account while signed in with it.")
    if auth.admin_count(db) <= 1:
        raise HTTPException(400, "At least one user must remain.")
    db.add(AuditLog(username=user.username, action="delete_admin", detail={"removed_user": u.username}))
    db.delete(u)
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/unlock")
def unlock_user(user_id: int, user: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found.")
    u.failed_logins, u.locked_until = 0, None
    db.add(AuditLog(username=user.username, action="unlock_admin", detail={"user": u.username}))
    db.commit()
    return _user_json(u)
