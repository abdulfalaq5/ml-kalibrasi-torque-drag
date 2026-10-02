"""Tanpa login, semua endpoint ditolak (kecuali health dan login)."""

import re

from fastapi.routing import APIRoute

PUBLIC = {"/api/health", "/api/auth/login"}


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path).replace("1:path", "x")


def test_every_api_route_requires_session(client):
    from app.main import app

    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api"):
            continue
        if route.path in PUBLIC:
            continue
        for method in route.methods:
            r = client.request(method, _concrete(route.path))
            assert r.status_code == 401, (method, route.path, r.status_code)
            checked += 1
    assert checked >= 15
    # rute yang tidak ada juga 401 (tidak membocorkan daftar endpoint)
    assert client.get("/api/tidak-ada").status_code == 401


def test_health_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["database"] == "OK"


def test_docs_disabled_in_production(monkeypatch):
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        app = create_app()
        paths = {getattr(r, "path", None) for r in app.routes}
        assert "/docs" not in paths and "/openapi.json" not in paths
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        get_settings.cache_clear()


def test_login_logout_me(auth_client):
    assert auth_client.get("/api/auth/me").json() == {"username": "admin"}
    assert auth_client.get("/api/wells").status_code == 200
    assert auth_client.post("/api/auth/logout").status_code == 200
    assert auth_client.get("/api/wells").status_code == 401


def test_session_cookie_flags(client):
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "password-uji-panjang"}
    )
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "max-age=28800" in cookie


def test_lockout_after_five_failures(client, db):
    from app.db.models import LoginAttempt
    from sqlalchemy import delete

    db.execute(delete(LoginAttempt))
    db.commit()
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "salah"})
        assert r.status_code == 401
    # percobaan keenam terkunci, bahkan dengan password benar
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "password-uji-panjang"}
    )
    assert r.status_code == 429
    db.execute(delete(LoginAttempt))
    db.commit()


def test_password_is_hashed(db):
    from app.db.models import AdminUser
    from sqlalchemy import select

    user = db.scalar(select(AdminUser))
    assert user.password_hash.startswith("$argon2")
    assert "password-uji-panjang" not in user.password_hash
