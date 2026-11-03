"""Server configuration, read from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AM_", env_file=".env")

    # Signing key for session cookies. MUST be set to a long random value in
    # production (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`).
    secret_key: str = "dev-insecure-change-me"

    database_url: str = "sqlite:///./accountability.db"

    # Where uploaded (blurred) capture images are stored on the server.
    media_dir: str = "./media"

    # Cookie lifetime in seconds (default 14 days).
    session_max_age: int = 14 * 24 * 3600


settings = Settings()
