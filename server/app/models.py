"""Database models.

A `User` is an account that can log in. The person being monitored owns
`Device`s that report `Event`s. A `Partnership` links a monitored user to an
accountability partner (also a `User`), who can view that user's events.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    display_name: str = ""
    created_at: datetime = Field(default_factory=_now)

    # Preferences.
    summary_frequency: str = "daily"  # daily | weekly | off

    # Billing (Stripe).
    stripe_customer_id: str | None = None
    subscription_status: str = "inactive"  # active | trialing | inactive


class Device(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    name: str = ""
    platform: str = ""
    # We store only a hash of the API key; the plaintext is shown once at
    # enrollment and never again.
    api_key_hash: str = Field(index=True)
    created_at: datetime = Field(default_factory=_now)
    last_seen: datetime | None = None


class Partnership(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # The monitored user whose events the partner may see.
    user_id: int = Field(index=True, foreign_key="user.id")
    # The partner's email (may be invited before they have an account).
    partner_email: str = Field(index=True)
    # Set once the partner accepts and has an account.
    partner_user_id: int | None = Field(default=None, foreign_key="user.id")
    status: str = "pending"  # pending | accepted
    created_at: datetime = Field(default_factory=_now)


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    device_id: int = Field(index=True, foreign_key="device.id")
    ts: datetime = Field(default_factory=_now, index=True)
    # flagged | capture_failure | heartbeat_miss
    kind: str = "flagged"
    reasons: str = ""
    score: float = 0.0
    image_path: str = ""  # server-relative path to the blurred capture, if any
