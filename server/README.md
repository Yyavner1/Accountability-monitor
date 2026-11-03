# Accountability Monitor — backend (SaaS)

A small FastAPI backend that turns the desktop agent into a hosted service:
accounts, device enrollment, an event-ingest API the agents report to, and a
web dashboard where an accountability partner signs in and sees a person's
flagged activity. Email from the agent still works independently; reporting
to this backend is additive.

> Status: MVP scaffold. Accounts, device API keys, event ingest, and the
> dashboard work. Billing and transactional email for invites are not built
> yet — see the roadmap in the top-level README.

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
- **Events:** `flagged`, `capture_failure`. Blurred captures are uploaded and
  served only to authorized viewers via `/captures/{name}`.
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

## Before this is production-ready

- Put it behind HTTPS (the capture images are sensitive).
- Move from SQLite to Postgres.
- Send real invite emails (currently a partner must sign up with the invited
  address to link).
- Add rate limiting and billing.
