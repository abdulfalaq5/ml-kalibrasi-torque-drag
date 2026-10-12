"""Manajemen akun (K-47): admin membuat, mengubah, dan menghapus akun yang boleh login.

Hanya admin (rute ini tidak ada di GUEST_ROUTES). Akun guest hanya melihat sumur monitoring
miliknya; admin melihat semua sumur.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.security import ROLES, current_user_id, hash_password
from app.db.models import AdminUser, LoginAttempt, UploadedFile, Well, utcnow
from app.db.session import get_db

router = APIRouter(prefix="/api/users", tags=["users"])

MIN_PASSWORD = 12  # sama dengan app.cli.MIN_LEN


class UserIn(BaseModel):
    username: str
    password: str
    role: str = "guest"


class UserPatch(BaseModel):
    username: str | None = None
    password: str | None = None
    role: str | None = None


def _user_out(u: AdminUser, n_wells: int) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
        "monitoring_wells": n_wells,
    }


def _username(db: Session, name: str, user_id: int | None = None) -> str:
    name = name.strip()
    if not 3 <= len(name) <= 64:
        raise HTTPException(400, "Username must be 3–64 characters")
    q = select(AdminUser.id).where(func.lower(AdminUser.username) == name.lower())
    if user_id is not None:
        q = q.where(AdminUser.id != user_id)
    if db.scalar(q) is not None:
        raise HTTPException(409, "This username is already used")
    return name


def _check_password(pw: str) -> None:
    if len(pw) < MIN_PASSWORD:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD} characters")


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise HTTPException(400, f"Role must be one of {', '.join(ROLES)}")


def _n_admins(db: Session) -> int:
    return db.scalar(select(func.count(AdminUser.id)).where(AdminUser.role == "admin")) or 0


def _get(db: Session, user_id: int) -> AdminUser:
    u = db.get(AdminUser, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    return u


def _wells_count(db: Session, user_id: int) -> int:
    q = select(func.count(Well.id)).where(Well.owner_id == user_id)
    return db.scalar(q) or 0


@router.get("")
def list_users(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(Well.owner_id, func.count(Well.id))
            .where(Well.owner_id.is_not(None))
            .group_by(Well.owner_id)
        ).all()
    )
    users = db.scalars(select(AdminUser).order_by(AdminUser.role, AdminUser.username))
    return [_user_out(u, counts.get(u.id, 0)) for u in users]


@router.post("", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db)):
    _check_role(body.role)
    _check_password(body.password)
    u = AdminUser(
        username=_username(db, body.username),
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(u)
    db.commit()
    return _user_out(u, 0)


@router.patch("/{user_id}")
def patch_user(user_id: int, body: UserPatch, request: Request, db: Session = Depends(get_db)):
    u = _get(db, user_id)
    if body.role is not None and body.role != u.role:
        _check_role(body.role)
        if u.role == "admin" and _n_admins(db) <= 1:
            raise HTTPException(400, "Cannot change the role of the only admin account")
        if u.id == current_user_id(request):
            raise HTTPException(400, "You cannot change your own role")
        u.role = body.role
    old_name = u.username
    if body.username is not None:
        u.username = _username(db, body.username, u.id)
    if body.password:
        _check_password(body.password)
        u.password_hash = hash_password(body.password)
        # buka kunci login setelah password diganti
        db.execute(delete(LoginAttempt).where(LoginAttempt.username == old_name))
    u.updated_at = utcnow()
    db.commit()
    if u.id == current_user_id(request) and u.username != old_name:
        request.session["user"] = u.username  # sesi sendiri tetap berlaku setelah ganti nama
    return _user_out(u, _wells_count(db, u.id))


@router.delete("/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Hapus akun. Sumur monitoring miliknya tetap ada (tanpa pemilik, hanya terlihat admin)."""
    u = _get(db, user_id)
    if u.id == current_user_id(request):
        raise HTTPException(400, "You cannot delete your own account")
    if u.role == "admin" and _n_admins(db) <= 1:
        raise HTTPException(400, "Cannot delete the only admin account")
    # eksplisit (SQLite uji tidak menegakkan ON DELETE SET NULL)
    db.execute(update(Well).where(Well.owner_id == u.id).values(owner_id=None))
    db.execute(
        update(UploadedFile).where(UploadedFile.uploaded_by == u.id).values(uploaded_by=None)
    )
    db.delete(u)
    db.commit()
    return {"ok": True}
