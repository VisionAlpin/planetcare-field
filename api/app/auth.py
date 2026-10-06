"""Anmeldung per E Mail Link (ohne Passwort) und Demo Zugang.

Ablauf
1. Landwirt gibt auf /login seine E Mail ein  → POST /api/auth/request-link
2. Ist die Adresse freigeschaltet, kommt eine E Mail mit Einmal Link (15 Minuten gültig)
3. Klick auf den Link                          → GET /auth/callback?token=…  setzt Sitzungs Cookie (30 Tage)
4. Abmelden                                    → POST /api/auth/logout

Demo: Anfragen mit Header "X-PCF-Mode: demo" (setzt das Frontend unter /demo) bekommen
einen Demo Nutzer: nur lesen, nur der Musterbetrieb (DEMO_FARM_ID).

Es gibt keine Selbstregistrierung. Nutzer legt ein Admin an:
    python -m app.auth add landwirt@example.at <farm_id> "Name"

Umgebungsvariablen (Render, Dienst pcf-api):
    PUBLIC_BASE_URL   https://www.planetcarefield.app
    DEMO_FARM_ID      UUID des Musterbetriebs
    SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, MAIL_FROM
    Ohne SMTP_HOST wird der Link nur ins Log geschrieben (Entwicklung).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import smtplib
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional

log = logging.getLogger("pcf.auth")

COOKIE_NAME = "pcf_session"
TOKEN_TTL = timedelta(minutes=15)
SESSION_TTL = timedelta(days=30)
MAX_LINKS_PER_HOUR = 5
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[a-z]{2,}$", re.I)


@dataclass
class CurrentUser:
    id: Optional[str]
    farm_id: str
    email: Optional[str]
    is_demo: bool = False
    role: str = "farmer"


# ---------------------------------------------------------------
# Hilfen (ohne Datenbank, testbar)
# ---------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> Optional[str]:
    e = (email or "").strip().lower()
    return e if EMAIL_RE.match(e) else None


def login_mail(link: str) -> tuple[str, str]:
    subject = "Ihr Anmeldelink für PlanetCare Field"
    body = (
        "Guten Tag,\n\n"
        "mit diesem Link melden Sie sich bei PlanetCare Field an:\n\n"
        f"{link}\n\n"
        "Der Link ist 15 Minuten gültig und funktioniert nur einmal.\n"
        "Wenn Sie keine Anmeldung angefordert haben, können Sie diese E Mail ignorieren.\n\n"
        "PlanetCare Field · VisionAlpin GmbH\n"
    )
    return subject, body


def send_mail(to: str, subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        log.warning("SMTP_HOST fehlt, Mail nicht gesendet. An %s: %s", to, body)
        return
    msg = EmailMessage()
    msg["From"] = os.environ["MAIL_FROM"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)


# ---------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------

def request_link(conn, email: str, base_url: str, mailer=send_mail) -> None:
    """Sendet einen Link, wenn die Adresse freigeschaltet ist. Antwortet nach außen IMMER gleich."""
    e = normalize_email(email)
    if not e:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT id::text FROM users WHERE email = %s AND active", (e,))
        r = cur.fetchone()
        if not r:
            log.info("Anmeldelink für unbekannte Adresse angefragt")
            return
        user_id = r[0]
        cur.execute(
            "SELECT count(*) FROM login_tokens WHERE user_id = %s AND created_at > now() - interval '1 hour'",
            (user_id,),
        )
        if cur.fetchone()[0] >= MAX_LINKS_PER_HOUR:
            log.warning("Zu viele Anmeldelinks für Nutzer %s", user_id)
            return
        token = new_secret()
        cur.execute(
            "INSERT INTO login_tokens (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (hash_secret(token), user_id, now_utc() + TOKEN_TTL),
        )
    conn.commit()
    subject, body = login_mail(f"{base_url.rstrip('/')}/auth/callback?token={token}")
    mailer(e, subject, body)


def consume_token(conn, token: str, user_agent: str = "") -> Optional[str]:
    """Gültiger, unbenutzter Link → neue Sitzung (Rückgabe: Sitzungsgeheimnis für das Cookie)."""
    if not token or len(token) > 200:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE login_tokens SET used_at = now() WHERE token_hash = %s AND used_at IS NULL AND expires_at > now() "
            "RETURNING user_id::text",
            (hash_secret(token),),
        )
        r = cur.fetchone()
        if not r:
            conn.commit()
            return None
        session = new_secret()
        cur.execute(
            "INSERT INTO sessions (session_hash, user_id, expires_at, user_agent) VALUES (%s, %s, %s, %s)",
            (hash_secret(session), r[0], now_utc() + SESSION_TTL, user_agent[:300]),
        )
        cur.execute("UPDATE users SET last_login = now() WHERE id = %s", (r[0],))
    conn.commit()
    return session


def user_from_session(conn, session: Optional[str]) -> Optional[CurrentUser]:
    if not session:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT u.id::text, u.farm_id::text, u.email, u.role FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.session_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now() AND u.active",
            (hash_secret(session),),
        )
        r = cur.fetchone()
    return CurrentUser(id=r[0], farm_id=r[1], email=r[2], role=r[3]) if r else None


def revoke_session(conn, session: Optional[str]) -> None:
    if not session:
        return
    with conn.cursor() as cur:
        cur.execute("UPDATE sessions SET revoked_at = now() WHERE session_hash = %s", (hash_secret(session),))
    conn.commit()


def demo_user() -> CurrentUser:
    return CurrentUser(id=None, farm_id=os.environ["DEMO_FARM_ID"], email=None, is_demo=True, role="demo")


# ---------------------------------------------------------------
# Router und Abhängigkeit current_user
# ---------------------------------------------------------------

try:
    import fastapi  # noqa: F401
except ImportError:  # nur in Tests ohne FastAPI
    fastapi = None

router = None
current_user = None
if fastapi is not None:
    from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
    from fastapi.responses import RedirectResponse
    from pydantic import BaseModel

    from .db import get_conn  # ANPASSEN

    class LinkRequest(BaseModel):
        email: str

    def current_user(request: Request, conn=Depends(get_conn)) -> CurrentUser:  # noqa: F811
        user = user_from_session(conn, request.cookies.get(COOKIE_NAME))
        if user:
            return user
        if request.headers.get("X-PCF-Mode") == "demo":
            return demo_user()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")

    router = APIRouter(tags=["Anmeldung"])

    @router.post("/api/auth/request-link", status_code=202)
    def post_request_link(body: LinkRequest, conn=Depends(get_conn)):
        request_link(conn, body.email, os.environ.get("PUBLIC_BASE_URL", "https://www.planetcarefield.app"))
        return {"message": "Wenn die Adresse freigeschaltet ist, kommt in wenigen Minuten eine E Mail."}

    @router.get("/auth/callback", include_in_schema=False)
    def get_callback(token: str, request: Request, conn=Depends(get_conn)):
        session = consume_token(conn, token, request.headers.get("user-agent", ""))
        if not session:
            return RedirectResponse("/login?fehler=link", status_code=303)
        resp = RedirectResponse("/dashboard", status_code=303)
        resp.set_cookie(COOKIE_NAME, session, max_age=int(SESSION_TTL.total_seconds()), httponly=True,
                        secure=True, samesite="lax", path="/")
        return resp

    @router.get("/api/auth/me")
    def get_me(user: CurrentUser = Depends(current_user)):
        return {"email": user.email, "farmId": user.farm_id, "isDemo": user.is_demo, "role": user.role}

    @router.post("/api/auth/logout", status_code=204)
    def post_logout(request: Request, conn=Depends(get_conn)):
        revoke_session(conn, request.cookies.get(COOKIE_NAME))
        resp = Response(status_code=204)
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp


# ---------------------------------------------------------------
# Admin: Nutzer anlegen
# ---------------------------------------------------------------

def _cli(argv: list[str]) -> None:
    if len(argv) < 3 or argv[0] != "add":
        raise SystemExit('Aufruf: python -m app.auth add <email> <farm_id> ["Name"]')
    e = normalize_email(argv[1])
    if not e:
        raise SystemExit("Ungültige E Mail Adresse")
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, farm_id, name) VALUES (%s, %s, %s) "
            "ON CONFLICT (email) DO UPDATE SET farm_id = EXCLUDED.farm_id, active = true RETURNING id",
            (e, argv[2], argv[3] if len(argv) > 3 else None),
        )
        print("Nutzer angelegt:", cur.fetchone()[0], e)


if __name__ == "__main__":
    _cli(sys.argv[1:])
