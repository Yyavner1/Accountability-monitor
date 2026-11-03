"""FastAPI application: accounts, device enrollment, event ingest, dashboard.

This server stores only text metadata about flagged moments — never
screenshots. See models.Event.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    Form,
    Header,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from . import auth, billing
from .config import settings
from .db import get_session, init_db
from .models import Device, Event, Partnership, User

SUMMARY_FREQUENCIES = {"daily", "weekly", "off"}

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Accountability Monitor")


@app.on_event("startup")
def _startup() -> None:
    init_db()


# --- helpers ---------------------------------------------------------------

def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


def _optional_user(request: Request, session: Session) -> User | None:
    raw = request.cookies.get(auth.SESSION_COOKIE)
    uid = auth.read_session_cookie(raw) if raw else None
    return session.get(User, uid) if uid else None


def _subscription_ok(user: User) -> bool:
    if not settings.require_subscription:
        return True
    return user.subscription_status in ("active", "trialing")


def _monitored_user_ids_for_partner(user: User, session: Session) -> list[int]:
    rows = session.exec(
        select(Partnership).where(
            Partnership.partner_user_id == user.id,
            Partnership.status == "accepted",
        )
    ).all()
    return [r.user_id for r in rows]


# --- auth pages ------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.post("/signup")
def signup(
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(""),
    session: Session = Depends(get_session),
):
    email = email.strip().lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status_code=400, detail="email already registered")
    user = User(
        email=email,
        password_hash=auth.hash_password(password),
        display_name=display_name or email,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # Link any pending partner invitations addressed to this email.
    pend = session.exec(
        select(Partnership).where(
            Partnership.partner_email == email, Partnership.status == "pending"
        )
    ).all()
    for p in pend:
        p.partner_user_id = user.id
        p.status = "accepted"
        session.add(p)
    session.commit()

    resp = _redirect("/")
    resp.set_cookie(
        auth.SESSION_COOKIE,
        auth.make_session_cookie(user.id),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return resp


@app.post("/login")
def login(
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    email = email.strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not auth.verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")
    resp = _redirect("/")
    resp.set_cookie(
        auth.SESSION_COOKIE,
        auth.make_session_cookie(user.id),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return resp


@app.get("/logout")
def logout():
    resp = _redirect("/login")
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


# --- landing + dashboard ---------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)):
    user = _optional_user(request, session)
    if not user:
        return templates.TemplateResponse(request, "landing.html", {})
    # Logged in: show the dashboard (or a subscribe prompt if gated).
    if not _subscription_ok(user):
        return templates.TemplateResponse(
            request, "subscribe_required.html", {"user": user}
        )
    # Events for this user's own devices, plus anyone they are a partner for.
    visible_ids = {user.id, *_monitored_user_ids_for_partner(user, session)}
    events = session.exec(
        select(Event).where(Event.user_id.in_(visible_ids))  # type: ignore[attr-defined]
        .order_by(Event.ts.desc()).limit(200)
    ).all()
    devices = session.exec(
        select(Device).where(Device.user_id == user.id)
    ).all()
    partners = session.exec(
        select(Partnership).where(Partnership.user_id == user.id)
    ).all()
    users = {u.id: u for u in session.exec(select(User)).all()}
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "events": events,
            "devices": devices,
            "partners": partners,
            "users": users,
        },
    )


@app.post("/devices")
def enroll_device(
    request: Request,
    name: str = Form(""),
    platform: str = Form(""),
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
):
    key = auth.new_api_key()
    device = Device(
        user_id=user.id,
        name=name or "device",
        platform=platform,
        api_key_hash=auth.hash_api_key(key),
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    # Show the plaintext key exactly once.
    return templates.TemplateResponse(
        request,
        "device_created.html",
        {"device": device, "api_key": key},
    )


@app.post("/partners")
def invite_partner(
    partner_email: str = Form(...),
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
):
    partner_email = partner_email.strip().lower()
    existing = session.exec(
        select(User).where(User.email == partner_email)
    ).first()
    p = Partnership(
        user_id=user.id,
        partner_email=partner_email,
        partner_user_id=existing.id if existing else None,
        status="accepted" if existing else "pending",
    )
    session.add(p)
    session.commit()
    return _redirect("/settings")


@app.post("/partners/remove")
def remove_partner(
    partnership_id: int = Form(...),
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
):
    p = session.get(Partnership, partnership_id)
    if p and p.user_id == user.id:
        session.delete(p)
        session.commit()
    return _redirect("/settings")


# --- settings, download, billing -------------------------------------------

@app.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
):
    partners = session.exec(
        select(Partnership).where(Partnership.user_id == user.id)
    ).all()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "user": user,
            "partners": partners,
            "billing_configured": billing.configured(),
        },
    )


@app.post("/settings/preferences")
def update_preferences(
    summary_frequency: str = Form("daily"),
    display_name: str = Form(""),
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
):
    if summary_frequency in SUMMARY_FREQUENCIES:
        user.summary_frequency = summary_frequency
    if display_name.strip():
        user.display_name = display_name.strip()
    session.add(user)
    session.commit()
    return _redirect("/settings")


@app.get("/download", response_class=HTMLResponse)
def download_page(
    request: Request, user: User = Depends(auth.current_user)
):
    return templates.TemplateResponse(
        request,
        "download.html",
        {"user": user, "agent_url": settings.agent_download_url},
    )


@app.post("/billing/checkout")
def billing_checkout(
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
):
    url = billing.create_checkout_session(user.email, user.stripe_customer_id)
    if not url:
        raise HTTPException(status_code=503, detail="billing not configured")
    return _redirect(url)


@app.post("/billing/portal")
def billing_portal(user: User = Depends(auth.current_user)):
    url = billing.create_billing_portal(user.stripe_customer_id or "")
    if not url:
        raise HTTPException(status_code=503, detail="no billing portal available")
    return _redirect(url)


@app.get("/billing/success", response_class=HTMLResponse)
def billing_success(request: Request, user: User = Depends(auth.current_user)):
    return templates.TemplateResponse(request, "billing_success.html", {"user": user})


@app.post("/billing/webhook")
async def billing_webhook(request: Request, session: Session = Depends(get_session)):
    event = billing.parse_webhook(
        await request.body(), request.headers.get("stripe-signature", "")
    )
    if not event:
        raise HTTPException(status_code=400, detail="invalid webhook")
    obj = event["data"]["object"]
    etype = event["type"]
    # Map the customer/email back to a user and update their status.
    email = obj.get("client_reference_id") or obj.get("customer_email")
    customer = obj.get("customer")
    user = None
    if email:
        user = session.exec(select(User).where(User.email == email.lower())).first()
    if not user and customer:
        user = session.exec(
            select(User).where(User.stripe_customer_id == customer)
        ).first()
    if user:
        if customer:
            user.stripe_customer_id = customer
        if etype in ("checkout.session.completed", "customer.subscription.created",
                     "customer.subscription.updated"):
            status_val = obj.get("status", "active")
            user.subscription_status = (
                "active" if status_val in ("active", "trialing", "complete", "paid")
                else status_val
            )
        elif etype in ("customer.subscription.deleted",):
            user.subscription_status = "inactive"
        session.add(user)
        session.commit()
    return {"ok": True}


# --- agent API -------------------------------------------------------------

def _device_auth(
    x_api_key: str = Header(...), session: Session = Depends(get_session)
) -> Device:
    device = auth.device_from_api_key(x_api_key, session)
    if not device:
        raise HTTPException(status_code=401, detail="invalid api key")
    return device


@app.post("/api/heartbeat")
def api_heartbeat(
    device: Device = Depends(_device_auth),
    session: Session = Depends(get_session),
):
    device.last_seen = datetime.now(timezone.utc)
    session.add(device)
    session.commit()
    return {"ok": True}


@app.post("/api/events")
def api_event(
    kind: str = Form("flagged"),
    reasons: str = Form(""),
    score: float = Form(0.0),
    context: str = Form(""),
    device: Device = Depends(_device_auth),
    session: Session = Depends(get_session),
):
    # Text metadata only. This endpoint intentionally accepts no image upload,
    # so no screenshot ever reaches or is stored on the server.
    device.last_seen = datetime.now(timezone.utc)
    session.add(device)
    ev = Event(
        user_id=device.user_id,
        device_id=device.id,
        kind=kind,
        reasons=reasons[:500],
        score=score,
        context=context[:500],
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return {"ok": True, "event_id": ev.id}
