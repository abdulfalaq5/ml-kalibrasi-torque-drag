from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./dev.db"
    secret_key: str = "dev-secret-key-ganti-di-production-minimal-32"
    session_hours: int = 8
    cookie_secure: bool = False
    max_upload_mb: int = 100
    upload_dir: Path = Path("./uploads")
    model_dir: Path = Path("./models")
    # Impor massal dari folder (paket 6 minggu)
    inbox_dir: Path = Path("./data/inbox")
    processed_dir: Path = Path("./data/processed")
    rejected_dir: Path = Path("./data/rejected")
    inbox_min_age_s: int = 60  # file yang baru diubah < 60 detik dilewati (mungkin masih disalin)
    inbox_move: bool = True  # pindahkan file ke processed/ atau rejected/ setelah impor
    static_dir: Path = Path(__file__).resolve().parents[2] / "static"

    admin_username: str | None = None
    admin_password: str | None = None

    # Penguncian login: 5 kali gagal -> kunci 15 menit
    login_max_failures: int = 5
    login_lock_minutes: int = 15

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
