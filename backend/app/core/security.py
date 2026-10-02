"""Hash password (argon2) dan dependensi sesi untuk satu akun admin."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request, status

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def require_admin(request: Request) -> str:
    """Dependensi untuk semua endpoint /api/* kecuali health dan login."""
    username = request.session.get("user")
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Belum login")
    return username
