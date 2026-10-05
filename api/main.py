"""PlanetCare Field — FastAPI Backend v0.4.1
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
    CropYear, DemandAggregate, DemandEvent, Farm, FieldProfile,
    IndicatorValue, Field, ProductLink,
)
from scoring import compute_field_profile
from app.scoring import finalize_overview

# ── Config ────────────────────────────────────────────────────────────────────

SERVICE_API_KEY = os.environ.get("SERVICE_API_KEY", "")
WEB_DIR = Path(__file__).parent.parent / "web"

app = FastAPI(
    title="PlanetCare Field API",
    version="0.4.1",
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
    return {"status": "ok", "version": "0.4.1", "lastJobRun": last_run}


# ── Overview endpoint (main dashboard data) ───────────────────────────────────

@app.get("/api/fields/{field_id}/overview")
def get_field_overview(
    field_id: str,
    season: int = None,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    """Return overview data matching the PCF_DEMO structure for the frontend."""
    # /demo path: use first field of demo farm, no auth
    is_demo = (field_id == "default" or field_id == "demo")

    if not is_demo:
        email = get_farmer_email(authorization)
        field = db.query(Field).join(Farm).filter(
            Field.id == field_id,
            Farm.owner_email == email,
        ).first()
    else:
        # Demo: find Musterbetrieb Flachgau
        demo_farm = db.query(Farm).filter(Farm.name == "Musterbetrieb Flachgau").first()
        if not demo_farm:
            raise HTTPException(status_code=404, detail="Demo data not seeded yet")
        field = db.query(Field).filter(Field.farm_id == demo_farm.id).first()

    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    farm = field.farm

    # Get seasons
    crop_years = (
        db.query(CropYear)
        .filter(CropYear.field_id == field.id)
        .order_by(CropYear.year.desc())
        .all()
    )
    if not crop_years:
        raise HTTPException(status_code=404, detail="No crop years found")

    target_year = season or crop_years[0].year
    cy = next((c for c in crop_years if c.year == target_year), crop_years[0])

    # Get latest profile for this crop year
    profile = (
        db.query(FieldProfile)
        .filter(FieldProfile.crop_year_id == cy.id)
        .order_by(FieldProfile.calculated_at.desc())
        .first()
    )

    # Get indicator sources
    indicators = db.query(IndicatorValue).filter(IndicatorValue.crop_year_id == cy.id).all()

    def source_info(indicator_names):
        hits = [i for i in indicators if i.indicator in indicator_names]
        if not hits:
            return None
        h = hits[-1]
        return {"source": h.source or "Sentinel-2", "date": str(h.acquired_at or date.today())}

    def score_block(score_val, indicator_names, explanation=""):
        if score_val is None:
            return {"available": False, "explanation": explanation}
        si = source_info(indicator_names)
        return {
            "available": True,
            "value": round(float(score_val)),
            "previousSeason": None,
            "regionalAverage": None,
            "source": si["source"] if si else "Methodik v1.0",
            "date": si["date"] if si else str(date.today()),
            "explanation": explanation,
        }

    # Build series from indicator history
    series = _build_series(db, field.id, crop_years)

    # Area from geometry (GeoJSON bbox estimate)
    try:
        from shapely.geometry import shape
        from pyproj import Geod
        geom = field.geom or {}
        s = shape(geom)
        geod = Geod(ellps="WGS84")
        area_ha = round(abs(geod.geometry_area_perimeter(s)[0]) / 10000, 1)
    except Exception:
        area_ha = float(field.area_ha or 0)

    seasons_list = [
        {"value": f"{field.id}:{c.year}", "label": f"{c.crop_type or 'Anbau'} {c.year}"}
        for c in crop_years
    ]

    hint_obj = None
    if profile and profile.score_biodiversity and float(profile.score_biodiversity) < 40:
        hint_obj = {
            "text": "Die Bodenvielfalt liegt unter dem regionalen Durchschnitt. Mögliche Ursachen: hohe Homogenität der Vegetation, geringe Randstrukturen.",
            "link": "#behandlungen",
        }

    result = {
        "farm": {"id": str(farm.id), "name": farm.name},
        "field": {
            "id": str(field.id),
            "name": field.name or "Schlag",
            "municipality": farm.region or "",
            "crop": cy.crop_type or "Anbau",
            "season": cy.year,
            "geometry": field.geom or {"type": "Polygon", "coordinates": [[[13.08, 47.92], [13.09, 47.92], [13.09, 47.91], [13.08, 47.91], [13.08, 47.92]]]},
        },
        "seasons": [c.year for c in crop_years],
        "fields": [
            {"id": str(f.id), "name": f.name or "Schlag"}
            for f in db.query(Field).filter(Field.farm_id == farm.id).all()
        ],
        "scores": {
            "water": score_block(profile.score_water if profile else None, ["ndvi_mean", "cdi"],
                explanation="Wie gut der Schlag Trockenphasen übersteht, gemessen an Dürrestufe (CDI) und Vegetationsverlauf."),
            "soil": score_block(profile.score_biodiversity if profile else None, ["ndvi_std"],
                explanation="Entwicklung der Bodengesundheit: räumliche Variabilität des Vegetationsindex."),
            "protection": score_block(profile.score_pesticide if profile else None, ["pesticide"],
                explanation="Pflanzenschutzbelastung basierend auf eingetragenen Behandlungen (kg Wirkstoff/ha)."),
        },
        "hint": hint_obj,
        "series": series,
        "methodology": {
            "version": profile.method_version if profile else "1.0",
            "computedAt": str(profile.calculated_at.date() if profile and profile.calculated_at else date.today()),
            "dataSources": ["Copernicus Sentinel-2", "EDO CDI"],
        },
    }

    # Vorsaison-Scores für previousSeason
    prev_year = target_year - 1
    prev_cy = next((c for c in crop_years if c.year == prev_year), None)
    previous_scores = {}
    if prev_cy:
        prev_profile = (
            db.query(FieldProfile)
            .filter(FieldProfile.crop_year_id == prev_cy.id)
            .order_by(FieldProfile.calculated_at.desc())
            .first()
        )
        if prev_profile:
            previous_scores = {
                "water": float(prev_profile.score_water) if prev_profile.score_water else None,
                "soil": float(prev_profile.score_biodiversity) if prev_profile.score_biodiversity else None,
                "protection": float(prev_profile.score_pesticide) if prev_profile.score_pesticide else None,
            }

    return finalize_overview(result, previous_scores)


def _build_series(db, field_id, crop_years):
    """Build time-series data for the trend chart."""
    series = []
    for cy in reversed(crop_years[-3:]):  # last 3 seasons
        profile = (
            db.query(FieldProfile)
            .filter(FieldProfile.crop_year_id == cy.id)
            .order_by(FieldProfile.calculated_at.desc())
            .first()
        )
        if profile:
            series.append({
                "label": str(cy.year),
                "date": f"{cy.year}-07-01",  # Mitte der Saison als X-Achsen-Datum
                "water": round(float(profile.score_water)) if profile.score_water else None,
                "soil": round(float(profile.score_biodiversity)) if profile.score_biodiversity else None,
                "protection": round(float(profile.score_pesticide)) if profile.score_pesticide else None,
                "total": round(float(profile.score_total)) if profile.score_total else None,
            })
    return series


# ── Field list ────────────────────────────────────────────────────────────────

@app.get("/api/fields")
def list_fields(db: Session = Depends(get_db), authorization: str = Header(None)):
    email = get_farmer_email(authorization)
    farm = db.query(Farm).filter(Farm.owner_email == email).first()
    if not farm:
        return {"fields": []}
    fields = db.query(Field).filter(Field.farm_id == farm.id).all()
    return {"fields": [{"id": str(f.id), "name": f.name} for f in fields]}


# ── Product field-profile (for PlanetCareScan server) ────────────────────────

@app.get("/api/products/{gtin}/field-profile", dependencies=[Depends(require_service_key)])
def get_product_field_profile(gtin: str, db: Session = Depends(get_db)):
    link = (
        db.query(ProductLink)
        .join(FieldProfile)
        .filter(ProductLink.gtin == gtin, FieldProfile.is_public == True)
        .order_by(FieldProfile.calculated_at.desc())
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="No public field profile linked to this GTIN")

    fp = link.profile
    cy = fp.crop_year
    field = cy.field
    farm = field.farm

    return {
        "gtin": gtin,
        "verified": True,
        "profileScore": round(float(fp.score_total)) if fp.score_total else None,
        "scores": {
            "water": round(float(fp.score_water)) if fp.score_water else None,
            "soil": round(float(fp.score_biodiversity)) if fp.score_biodiversity else None,
            "protection": round(float(fp.score_pesticide)) if fp.score_pesticide else None,
        },
        "region": farm.region,
        "harvestYear": cy.year,
        "methodology": fp.method_version or "v1.0",
    }


# ── Demand events (from PlanetCareScan server) ────────────────────────────────

class DemandEventIn(BaseModel):
    events: list[dict]


@app.post("/api/demand-events", dependencies=[Depends(require_service_key), Depends(check_rate_limit)])
def post_demand_events(body: DemandEventIn, db: Session = Depends(get_db)):
    stored = 0
    for e in body.events:
        ev = DemandEvent(
            event_type=e.get("type", "unknown"),
            gtin=e.get("gtin"),
            compared_with=json.dumps(e.get("comparedWith", [])),
            category=e.get("category"),
            region=e.get("region"),
            calendar_week=e.get("week"),
            panel=e.get("panel", False),
            willingness_to_pay=e.get("wtpPct"),
        )
        db.add(ev)
        stored += 1
    db.commit()
    return {"ok": True, "stored": stored}


# ── Market signal (dashboard) ─────────────────────────────────────────────────

@app.get("/api/market-signal")
def get_market_signal(region: str = None, category: str = None, db: Session = Depends(get_db)):
    q = db.query(DemandAggregate)
    if region:
        q = q.filter(DemandAggregate.region == region)
    if category:
        q = q.filter(DemandAggregate.category == category)
    rows = q.order_by(DemandAggregate.updated_at.desc()).limit(50).all()
    return {
        "results": [
            {
                "category": r.category,
                "region": r.region,
                "calendar_week": r.calendar_week,
                "n_events": r.n_events,
                "preference_rate": float(r.preference_rate) if r.preference_rate else None,
                "wtp_median": float(r.wtp_median) if r.wtp_median else None,
                "has_panel": r.has_panel,
            }
            for r in rows
        ]
    }


# ── Serve frontend ────────────────────────────────────────────────────────────

if WEB_DIR.exists():
    @app.get("/demo", response_class=HTMLResponse)
    @app.get("/dashboard", response_class=HTMLResponse)
    async def serve_app(request: Request):
        return (WEB_DIR / "index.html").read_text()

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        return (WEB_DIR / "index.html").read_text()

    # Statische Dateien: styles/, js/, data/, manifest.json etc.
    # Explizite Routen für Unterordner damit /api/* nicht überschrieben wird
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
