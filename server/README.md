# Accountability Monitor — backend (SaaS)

A small FastAPI backend that turns the desktop agent into a hosted service:
accounts, device enrollment, an event-ingest API the agents report to, and a
web dashboard where an accountability partner signs in and sees a person's
flagged activity. Email from the agent still works independently; reporting
to this backend is additive.

> Status: MVP. Accounts, a public landing page, a download page, device API
> keys, event ingest, the dashboard, a settings page (email frequency, add /
> remove partners), and Stripe subscription billing all work. Billing is
> optional and off until Stripe keys are set. Transactional invite email and
> server-side scheduled summaries are the remaining pieces.

## Pages

| path | who | purpose |
|---|---|---|
| `/` | public / logged in | landing page, or the dashboard when signed in |
| `/login` | public | sign in / create account |
| `/settings` | user | name, summary frequency, partners, subscription |
| `/download` | user | download the agent + setup steps |
| `/api/events`, `/api/heartbeat` | agents | report activity (X-API-Key) |
| `/billing/checkout`, `/billing/portal`, `/billing/webhook` | user / Stripe | subscription |

## Run locally

```bash
cd server
./run.sh        # http://127.0.0.1:8000
```

Open http://127.0.0.1:8000/login, create an account, enroll a device (you
get an API key once), and invite a partner by email.

## How the pieces connect

```
  desktop agent ──X-API-Key──► POST /api/events   ─┐
                 ──X-API-Key──► POST /api/heartbeat ├─► SQLite
  partner ──cookie session──► GET / (dashboard) ◄───┘
```

- **Accounts:** email + password (bcrypt), signed session cookie.
- **Devices:** each enrolled device gets an API key; only its SHA-256 hash is
  stored. The agent sends it as the `X-API-Key` header.
- **Events:** `flagged`, `capture_failure`, `filter_tampered` — **text
  metadata only**. The server never receives or stores a screenshot. Any
  visual the partner sees is emailed to them directly by the agent, never
  routed through or kept on the server. This is the main privacy/legal
  safeguard (the Accountable2You model rather than the screenshot-to-server
  model).
- **Partners:** invite by email; when that email signs up, the pending
  partnership is auto-accepted and they can view the inviter's events.

## Point an agent at it

In the agent's `config.json`:

```json
"server_url": "https://your-server.example.com",
"device_api_key": "am_...the key shown at enrollment..."
```

## Configuration (environment, prefix `AM_`)

| var | meaning |
|---|---|
| `AM_SECRET_KEY` | session cookie signing key (set a long random value) |
| `AM_DATABASE_URL` | SQLAlchemy URL (default local SQLite) |
| `AM_MEDIA_DIR` | where uploaded blurred captures are stored |
| `AM_PUBLIC_URL` | public base URL (Stripe redirect targets) |
| `AM_STRIPE_SECRET_KEY` | Stripe secret key (`sk_...`); empty = billing off |
| `AM_STRIPE_PRICE_ID` | recurring price id (`price_...`) |
| `AM_STRIPE_WEBHOOK_SECRET` | webhook signing secret (`whsec_...`) |
| `AM_REQUIRE_SUBSCRIPTION` | `true` gates access on an active subscription |

## Enabling billing

1. Create a Stripe account and a recurring **Price** for the subscription.
2. Set `AM_STRIPE_SECRET_KEY` and `AM_STRIPE_PRICE_ID`.
3. Add a webhook endpoint pointing at `/billing/webhook` for the events
   `checkout.session.completed` and `customer.subscription.*`, and set
   `AM_STRIPE_WEBHOOK_SECRET`.
4. Set `AM_REQUIRE_SUBSCRIPTION=true` to require a subscription to use it.

## Before this is production-ready

- Put it behind HTTPS (the capture images are sensitive).
- Move from SQLite to Postgres.
- Send real invite emails (currently a partner must sign up with the invited
  address to link).
- Add rate limiting and billing.
