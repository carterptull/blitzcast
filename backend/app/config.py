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

    anthropic_model: str = "claude-haiku-4-5-20251001"

    cors_origins: str = "http://localhost:3000"

    # Serve fixture predictions so the frontend works before real data exists.
    blitzcast_mock: bool = False

    model_version: str = "0.1.0"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
