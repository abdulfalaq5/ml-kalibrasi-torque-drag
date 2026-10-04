import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from app.api import (
    auth,
    datasets,
    evaluations,
    files,
    health,
    inbox,
    limits,
    models,
    quality,
    templates,
    wells,
)
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.security import hash_password, require_admin
from app.db.models import AdminUser
from app.db.session import SessionLocal

log = logging.getLogger(__name__)


def ensure_admin() -> None:
    """Buat akun admin dari ADMIN_USERNAME/ADMIN_PASSWORD bila belum ada akun sama sekali."""
    s = get_settings()
    with SessionLocal() as db:
        if db.scalar(select(AdminUser.id).limit(1)) is not None:
            if s.admin_password:
                log.warning(
                    "ADMIN_PASSWORD is still set in .env. Remove it now that the account exists."
                )
            return
        if not (s.admin_username and s.admin_password):
            log.warning("No admin account yet. Set ADMIN_USERNAME and ADMIN_PASSWORD in .env.")
            return
        db.add(AdminUser(username=s.admin_username, password_hash=hash_password(s.admin_password)))
        try:
            db.commit()
        except IntegrityError:  # worker uvicorn lain membuatnya lebih dulu
            db.rollback()
            return
        log.info("Admin account '%s' created. Remove ADMIN_PASSWORD from .env.", s.admin_username)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    s = get_settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    s.model_dir.mkdir(parents=True, exist_ok=True)
    try:
        ensure_admin()
    except Exception as exc:  # tabel belum ada (migrasi belum jalan)
        log.error("Cannot check the admin account: %s", exc)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    if s.is_production and (len(s.secret_key) < 32 or s.secret_key.startswith("dev-")):
        raise RuntimeError("In production SECRET_KEY must be random and at least 32 characters")

    app = FastAPI(
        title="Torque & Drag ML Calibration",
        lifespan=lifespan,
        docs_url=None if s.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if s.is_production else "/openapi.json",
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=s.secret_key,
        session_cookie="tdml_session",
        max_age=s.session_hours * 3600,
        same_site="lax",
        https_only=s.cookie_secure,
    )

    # Publik: health dan login. Selain itu wajib sesi admin.
    app.include_router(health.router)
    app.include_router(auth.router)
    protected = [Depends(require_admin)]
    app.include_router(files.router, dependencies=protected)
    app.include_router(wells.router, dependencies=protected)
    app.include_router(models.router, dependencies=protected)
    for r in (
        inbox.router,
        quality.router,
        datasets.router,
        limits.router,
        evaluations.router,
        templates.router,
    ):
        app.include_router(r, dependencies=protected)

    @app.api_route(
        "/api/{rest:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        dependencies=protected,
        include_in_schema=False,
    )
    def api_not_found(rest: str):
        raise HTTPException(404, "Endpoint not found")

    static_dir = Path(s.static_dir)

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        # Halaman web (SPA). Login ditangani di sisi klien; data tetap dilindungi API.
        target = (static_dir / path).resolve()
        if path and target.is_file() and target.is_relative_to(static_dir.resolve()):
            return FileResponse(target)
        index = static_dir / "index.html"
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return {"detail": "Frontend is not built yet (run npm run build in web/)"}

    return app


app = create_app()
