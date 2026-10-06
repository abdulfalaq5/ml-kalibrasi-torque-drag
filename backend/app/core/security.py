"""Hash password (argon2) dan dependensi sesi: akun admin + akun guest (K-45)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db

_hasher = PasswordHasher()

ROLES = ("admin", "guest")

# Guest: hanya menu Monitoring dan Dashboard, hanya sumur monitoring. Ekspor Excel/PDF ditutup
# karena berisi kurva WellPlan; promote ke training, model, kualitas, dll. hanya untuk admin.
GUEST_ROUTES = {
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/wells"),
    ("GET", "/api/wells/{well_id}"),
    ("PATCH", "/api/wells/{well_id}"),
    ("DELETE", "/api/wells/{well_id}"),
    ("POST", "/api/wells/{well_id}/predict"),
    ("GET", "/api/wells/{well_id}/profile"),
    ("POST", "/api/wells/{well_id}/forecast"),
    ("GET", "/api/files"),
    ("POST", "/api/files"),
    ("GET", "/api/files/{file_id}/download"),
    ("GET", "/api/templates/{kind}.xlsx"),
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def is_guest(request: Request) -> bool:
    return getattr(request.state, "role", "admin") == "guest"


def _guest_scope(request: Request, db: Session) -> None:
    """Guest hanya boleh rute di GUEST_ROUTES dan hanya sumur/file monitoring."""
    from app.db.models import UploadedFile, Well

    route = request.scope.get("route")
    if (request.method, getattr(route, "path", None)) not in GUEST_ROUTES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available for the guest account")
    pp = request.path_params
    if "well_id" in pp:
        w = db.get(Well, int(pp["well_id"]))
        if w is None or w.purpose != "monitoring":
            raise HTTPException(404, "Well not found")
    if "file_id" in pp:
        f = db.get(UploadedFile, int(pp["file_id"]))
        if f is None or f.purpose != "monitoring":
            raise HTTPException(404, "File not found")
    if "kind" in pp and pp["kind"] != "monitoring":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available for the guest account")


def require_admin(request: Request, db: Session = Depends(get_db)) -> str:
    """Dependensi untuk semua endpoint /api/* kecuali health dan login.

    Nama tetap (dipakai di main.py); peran dibaca dari database setiap request, jadi akun yang
    dihapus atau diubah perannya langsung berlaku.
    """
    from app.db.models import AdminUser

    username = request.session.get("user")
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    user = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if user is None:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    request.state.role = user.role or "admin"
    if request.state.role == "guest":
        _guest_scope(request, db)
    return username
