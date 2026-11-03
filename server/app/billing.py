"""Stripe subscription billing (optional).

All functions degrade gracefully when Stripe is not configured, so the app
runs fully in development without any keys. Set these env vars to enable it:

    AM_STRIPE_SECRET_KEY      sk_...
    AM_STRIPE_PRICE_ID        price_...   (a recurring price)
    AM_STRIPE_WEBHOOK_SECRET  whsec_...
    AM_REQUIRE_SUBSCRIPTION   true        (gate access on an active sub)
"""

from __future__ import annotations

import logging

from .config import settings

log = logging.getLogger("billing")


def configured() -> bool:
    return bool(settings.stripe_secret_key and settings.stripe_price_id)


def _stripe():
    import stripe  # imported lazily so the dep is optional at runtime

    stripe.api_key = settings.stripe_secret_key
    return stripe


def create_checkout_session(user_email: str, customer_id: str | None) -> str | None:
    """Return a Stripe Checkout URL for a new subscription, or None."""
    if not configured():
        return None
    stripe = _stripe()
    kwargs = dict(
        mode="subscription",
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url=f"{settings.public_url}/billing/success",
        cancel_url=f"{settings.public_url}/settings",
        client_reference_id=user_email,
    )
    if customer_id:
        kwargs["customer"] = customer_id
    else:
        kwargs["customer_email"] = user_email
    session = stripe.checkout.Session.create(**kwargs)
    return session.url


def create_billing_portal(customer_id: str) -> str | None:
    """Return a Stripe customer-portal URL to manage/cancel the subscription."""
    if not configured() or not customer_id:
        return None
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=customer_id, return_url=f"{settings.public_url}/settings"
    )
    return session.url


def parse_webhook(payload: bytes, signature: str):
    """Verify and parse a Stripe webhook event, or return None."""
    if not settings.stripe_webhook_secret:
        return None
    stripe = _stripe()
    try:
        return stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret
        )
    except Exception as exc:  # pragma: no cover - depends on Stripe
        log.warning("invalid stripe webhook: %s", exc)
        return None
