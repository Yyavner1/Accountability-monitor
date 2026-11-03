"""FastAPI application: accounts, device enrollment, event ingest, dashboard."""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from . import auth
from .config import settings
from .db import get_session, init_db
from .models import Device, Event, Partnership, User

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Accountability Monitor")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    Path(settings.media_dir).mkdir(parents=True, exist_ok=True)


# Serve blurred captures. These are sensitive, so the directory is only
# reachable through the authenticated /captures/{id} route below, not here.
app.mount(
    "/static", StaticFiles(directory=str(BASE_DIR / "static"), check_dir=False),
    name="static",
)


# --- helpers ---------------------------------------------------------------

def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


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


# --- dashboard -------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
):
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
    return _redirect("/")


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
    image: UploadFile | None = File(None),
    device: Device = Depends(_device_auth),
    session: Session = Depends(get_session),
):
    image_path = ""
    if image is not None:
        media_dir = Path(settings.media_dir)
        media_dir.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.jpg"
        dest = media_dir / name
        with open(dest, "wb") as f:
            shutil.copyfileobj(image.file, f)
        image_path = name

    device.last_seen = datetime.now(timezone.utc)
    session.add(device)
    ev = Event(
        user_id=device.user_id,
        device_id=device.id,
        kind=kind,
        reasons=reasons,
        score=score,
        image_path=image_path,
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return {"ok": True, "event_id": ev.id}


@app.get("/captures/{name}")
def get_capture(
    name: str,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
):
    # Only serve a capture if it belongs to a user this account may view.
    ev = session.exec(select(Event).where(Event.image_path == name)).first()
    if not ev:
        raise HTTPException(status_code=404, detail="not found")
    visible = {user.id, *_monitored_user_ids_for_partner(user, session)}
    if ev.user_id not in visible:
        raise HTTPException(status_code=403, detail="forbidden")
    path = Path(settings.media_dir) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    from fastapi.responses import FileResponse

    return FileResponse(str(path), media_type="image/jpeg")
