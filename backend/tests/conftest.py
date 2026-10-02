import os
import sys
import tempfile
from pathlib import Path

# Lingkungan uji: SQLite sementara, harus di-set sebelum app diimpor
_TMP = Path(tempfile.mkdtemp(prefix="tdml-test-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
        "UPLOAD_DIR": str(_TMP / "uploads"),
        "MODEL_DIR": str(_TMP / "models"),
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "password-uji-panjang",
        "SECRET_KEY": "kunci-rahasia-uji-minimal-32-karakter-xx",
        "COOKIE_SECURE": "false",
    }
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402
from app.db.models import Base, LoginAttempt  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
Base.metadata.create_all(engine)


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    with SessionLocal() as s:
        s.execute(delete(LoginAttempt))
        s.commit()
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "password-uji-panjang"}
    )
    assert r.status_code == 200
    return client


@pytest.fixture(scope="session")
def tmp_dir() -> Path:
    return _TMP
