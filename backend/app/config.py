"""Application settings loaded from environment / backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://blitzcast:blitzcast@localhost:5432/blitzcast"

    # Job-specific keys: validated lazily by the scripts that need them.
    odds_api_key: str = ""
    visual_crossing_api_key: str = ""
    anthropic_api_key: str = ""
    cfbd_api_key: str = ""

    anthropic_model: str = "claude-haiku-4-5-20251001"

    cors_origins: str = "http://localhost:3000"

    # Serve fixture predictions so the frontend works before real data exists.
    blitzcast_mock: bool = False

    # NFL keeps the original stamp; CFB artifacts/predictions use their own.
    model_version: str = "1.0.0"
    model_version_cfb: str = "cfb-1.0.0"

    def model_version_for(self, sport: str) -> str:
        return self.model_version_cfb if sport.upper() == "CFB" else self.model_version

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
