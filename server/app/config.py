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

    # Public base URL of this server (used for Stripe redirect URLs).
    public_url: str = "http://127.0.0.1:8000"

    # Billing (Stripe). Leave the keys empty to run without billing; set
    # require_subscription=True only once Stripe is configured.
    stripe_secret_key: str = ""
    stripe_price_id: str = ""
    stripe_webhook_secret: str = ""
    require_subscription: bool = False

    # Where to download the desktop agent from (shown on the download page).
    agent_download_url: str = (
        "https://github.com/yyavner1/accountability-monitor/archive/refs/heads/main.zip"
    )

    # Set True in production (behind HTTPS) so session cookies are Secure.
    secure_cookies: bool = False

    # Outbound email for verification / password reset. If unset, the link is
    # logged to the server console instead of sent (fine for local testing).
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""


settings = Settings()
