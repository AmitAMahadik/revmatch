"""Load config from environment via Pydantic Settings. No secrets in repo."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Optional local convenience only. Do not commit a real .env file to git.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Connection / DB
    mongodb_url: str = Field(..., validation_alias="MONGODB_URL")
    db_name: str = Field("porsche", validation_alias="DB_NAME")

    # App runtime
    env: str = Field("dev", validation_alias="ENV")

    # Comma-separated list of allowed origins, e.g. "https://example.com,http://localhost:5173"
    # Use "*" to allow all.
    cors_origins: list[str] = Field(default_factory=list, validation_alias="CORS_ORIGINS")

    # Optional DB ping during /health
    health_db_check: bool = Field(False, validation_alias="HEALTH_DB_CHECK")

    # OpenAI (optional)
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")

    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s == "*":
                return ["*"]
            return [p.strip() for p in s.split(",") if p.strip()]
        return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Cached settings loader (env vars are read once per process).

    Note: Pydantic BaseSettings populates required fields from environment
    variables at runtime. Static type checkers (e.g. pyright) cannot see that,
    so we silence the call-arg warning here.
    """
    return Settings()  # pyright: ignore[reportCallIssue]
