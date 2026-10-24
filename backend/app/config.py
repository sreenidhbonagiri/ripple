"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py → repo root is parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INP = REPO_ROOT / "data" / "L-TOWN.inp"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ripple_inp_path: Path = DEFAULT_INP
    ripple_host: str = "127.0.0.1"
    ripple_port: int = 8000
    # Tiger Cloud / TimescaleDB (loaded from project-root .env)
    database_url: str | None = None
    # Required for imports: Tiger Console service storage limit (bytes). No default.
    ripple_storage_limit_bytes: int | None = None
    # Optional override for January raw/CAGG benchmark artifact path
    ripple_benchmark_artifact: Path | None = None
    # Comma-separated CORS origins for deployed frontends (optional)
    ripple_cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
