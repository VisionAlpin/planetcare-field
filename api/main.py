"""PlanetCare Field — FastAPI Backend v0.6.0
Render PostgreSQL (SQLAlchemy) statt Supabase.
"""

import json
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
import time
import collections

from database import get_db
from models import (
    CropYear, Farm, FieldProfile,
    IndicatorValue, Field, ProductLink,
)
from scoring import compute_field_profile
from app.scoring import finalize_overview

# ── Config ────────────────────────────────────────────────────────────────────

SERVICE_API_KEY = os.environ.get("SERVICE_API_KEY", "")
WEB_DIR = Path(__file__).parent.parent / "web"

app = FastAPI(
    title="PlanetCare Field API",
    version="0.6.0",
    description="Sustainability scoring for agricultural fields (NOSTRADAMUS / Horizon Europe TRL-4)",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Security Headers ──────────────────────────────────────────────────────────

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'"
    )
    return response

# ── Rate Limiting für /api/demand-events ─────────────────────────────────────

_rate_buckets: dict = collections.defaultdict(list)
RATE_LIMIT = 60  # Anfragen pro Minute je IP

def check_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _rate_buckets[ip]
    # Alte Einträge löschen (älter als 60s)
    _rate_buckets[ip] = [t for t in bucket if now - t < 60]
    if len(_rate_buckets[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded (60/min)")
    _rate_buckets[ip].append(now)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def require_service_key(authorization: str = Header(None)):
    """For /api/products and /api/demand-events — called from PlanetCareScan server."""
    if not authorization or authorization != f"Bearer {SERVICE_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing SERVICE_API_KEY")


def get_farmer_email(authorization: str = Header(None)) -> str:
    """Very simple email-token auth for Phase 0. Replace with magic link in Phase 1."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    # For Phase 0 demo: token IS the email (protected by HTTPS + invite-only)
    # Phase 1: exchange for signed JWT from email link
    return authorization.split(" ", 1)[1]


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health(db: Session = Depends(get_db)):
    # Letzten Job-Run aus job_runs Tabelle lesen (falls schon angelegt)
    last_run = None
    try:
        from sqlalchemy import text
        row = db.execute(text(
            "SELECT finished_at, status, fields_ok, fields_failed FROM job_runs ORDER BY id DESC LIMIT 1"
        )).fetchone()
        if row:
            last_run = {
                "finishedAt": row[0].isoformat() if row[0] else None,
                "status": row[1],
                "fieldsOk": row[2],
                "fieldsFailed": row[3],
            }
    except Exception:
        pass
    return {"status": "ok", "version": "0.6.0", "lastJobRun": last_run}


# ── Overview endpoint (main dashboard data) ───────────────────────────────────

@app.get("/api/fields")
def list_fields(db: Session = Depends(get_db), authorization: str = Header(None)):
    email = get_farmer_email(authorization)
    farm = db.query(Farm).filter(Farm.owner_email == email).first()
    if not farm:
        return {"fields": []}
    fields = db.query(Field).filter(Field.farm_id == farm.id).all()
    return {"fields": [{"id": str(f.id), "name": f.name} for f in fields]}


# ── Routers v0.6.0 ────────────────────────────────────────────────────────────
try:
    from .app.measures import router as measures_router
    from .app.bridge import router as bridge_router
    from .app.overview import router as overview_router
    from .app.auth import router as auth_router
    from .app.pages import router as pages_router
except ImportError:
    from app.measures import router as measures_router
    from app.bridge import router as bridge_router
    from app.overview import router as overview_router
    from app.auth import router as auth_router
    from app.pages import router as pages_router

app.include_router(overview_router)   # ersetzt alten /api/fields/{id}/overview
app.include_router(measures_router)
app.include_router(bridge_router)
app.include_router(auth_router)
app.include_router(pages_router)      # ersetzt /demo, /dashboard, /login, /


# ── Serve frontend ────────────────────────────────────────────────────────────
# /demo, /dashboard, /login, / werden von pages_router bedient

if WEB_DIR.exists():
    # Statische Dateien: styles/, js/, data/, manifest.json etc.
    from fastapi.responses import FileResponse as FR

    @app.get("/styles/{path:path}")
    async def serve_styles(path: str):
        f = WEB_DIR / "styles" / path
        if f.exists():
            return FR(str(f))
        raise HTTPException(status_code=404)

    @app.get("/js/{path:path}")
    async def serve_js(path: str):
        f = WEB_DIR / "js" / path
        if f.exists():
            return FR(str(f))
        raise HTTPException(status_code=404)

    @app.get("/data/{path:path}")
    async def serve_data(path: str):
        f = WEB_DIR / "data" / path
        if f.exists():
            return FR(str(f))
        raise HTTPException(status_code=404)

    @app.get("/manifest.json")
    async def serve_manifest():
        f = WEB_DIR / "manifest.json"
        if f.exists():
            return FR(str(f), media_type="application/manifest+json")
        raise HTTPException(status_code=404)

    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_favicon():
        f = WEB_DIR / "favicon.ico"
        if f.exists():
            return FR(str(f), media_type="image/x-icon",
                      headers={"Cache-Control": "public, max-age=604800"})
        raise HTTPException(status_code=404)

    @app.get("/icons/{path:path}")
    async def serve_icons(path: str):
        f = WEB_DIR / "icons" / path
        if f.exists():
            return FR(str(f))
        raise HTTPException(status_code=404)

    @app.get("/fonts/{path:path}")
    async def serve_fonts(path: str):
        f = WEB_DIR / "fonts" / path
        if f.exists():
            return FR(str(f))
        raise HTTPException(status_code=404)

    @app.get("/sw.js")
    async def serve_sw():
        f = WEB_DIR / "sw.js"
        if f.exists():
            return FR(str(f))
        raise HTTPException(status_code=404)
