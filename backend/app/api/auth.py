from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_admin, verify_password
from app.db.models import AdminUser, LoginAttempt
from app.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


def _is_locked(db: Session, username: str) -> bool:
    s = get_settings()
    since = datetime.now(UTC) - timedelta(minutes=s.login_lock_minutes)
    last_ok = db.scalar(
        select(func.max(LoginAttempt.created_at)).where(
            LoginAttempt.username == username, LoginAttempt.success.is_(True)
        )
    )
    if last_ok is not None:
        if last_ok.tzinfo is None:
            last_ok = last_ok.replace(tzinfo=UTC)
        since = max(since, last_ok)
    failures = db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.username == username,
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at > since,
        )
    )
    return failures >= s.login_max_failures


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    username = body.username.strip()[:64]
    ip = request.client.host if request.client else None
    if _is_locked(db, username):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {get_settings().login_lock_minutes} minutes.",
        )
    user = db.scalar(select(AdminUser).where(AdminUser.username == username))
    ok = user is not None and verify_password(user.password_hash, body.password)
    db.add(LoginAttempt(username=username, ip=ip, success=ok))
    db.commit()
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    request.session.clear()
    request.session["user"] = user.username
    return {"username": user.username}


@router.post("/logout")
def logout(request: Request, _: str = Depends(require_admin)):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user: str = Depends(require_admin)):
    return {"username": user}
