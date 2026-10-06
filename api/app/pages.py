"""Seiten: /dashboard nur mit Anmeldung, /demo und /login offen.

Einbau in main.py (bestehende Routen /dashboard und /demo ersetzen):
    from .pages import router as pages_router
    app.include_router(pages_router)
WEB_DIR an den Ort des Frontends anpassen.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse

from .auth import COOKIE_NAME, user_from_session
from .db import get_conn  # ANPASSEN

WEB_DIR = Path(__file__).resolve().parents[2] / "web"   # ANPASSEN
NO_CACHE = {"Cache-Control": "no-cache"}

router = APIRouter(include_in_schema=False)


@router.get("/dashboard")
def dashboard(request: Request, conn=Depends(get_conn)):
    if not user_from_session(conn, request.cookies.get(COOKIE_NAME)):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE)


@router.get("/demo")
def demo():
    return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE)


@router.get("/login")
def login():
    return FileResponse(WEB_DIR / "login.html", headers=NO_CACHE)


@router.get("/")
def root():
    return RedirectResponse("/demo", status_code=307)
