"""PlanetCare Field — FastAPI Backend v0.1.0"""

import os
import uuid
import asyncio
from datetime import date, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from satellite import fetch_ndvi_for_field, fetch_cdi_for_point, geojson_bbox
from scoring import compute_field_profile

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON = os.getenv("SUPABASE_ANON", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

app = FastAPI(
    title="PlanetCare Field API",
    version="0.1.0",
    description="Sustainability scoring for agricultural fields — Phase 0 (NOSTRADAMUS/Horizon Europe TRL-4)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store (Phase 0 — replace with Redis/DB for production)
_jobs: dict[str, dict] = {}


# ──────────────────────────────────────────────
# Supabase helpers
# ──────────────────────────────────────────────

def sb_headers(use_service_key: bool = False) -> dict:
    key = SUPABASE_SERVICE_KEY if use_service_key else SUPABASE_ANON
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def sb_headers_authed(token: str) -> dict:
    return {
        "apikey": SUPABASE_ANON,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def sb_get(path: str, params: dict = None, token: str = None, service: bool = False):
    headers = sb_headers_authed(token) if token else sb_headers(service)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=headers, params=params, timeout=15)
        return r


async def sb_post(path: str, data: dict, service: bool = False):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers=sb_headers(service),
            json=data,
            timeout=15,
        )
        return r


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────

class DemandSignalIn(BaseModel):
    category: Optional[str] = None
    region: Optional[str] = None
    chose_better_field_profile: Optional[bool] = None
    willingness_to_pay_pct: Optional[float] = None
    is_panel: bool = False
    panel_code: Optional[str] = None


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/products/{gtin}/field-profile")
async def get_product_field_profile(gtin: str):
    """Return public field profile linked to a GTIN."""
    r = await sb_get(
        "pcf_product_links",
        params={
            "gtin": f"eq.{gtin}",
            "select": "gtin,batch_id,linked_at,pcf_field_profiles!inner(score_total,score_water,score_biodiversity,score_pesticide,method_version,calculated_at,is_public,pcf_crop_years!inner(year,crop_type,pcf_fields!inner(name,area_ha,geometry,pcf_farms!inner(name,region,country))))",
        },
        service=True,
    )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="No public field profile linked to this GTIN")

    rows = r.json()
    # Filter public profiles
    public = [row for row in rows if row.get("pcf_field_profiles", {}).get("is_public")]
    if not public:
        raise HTTPException(status_code=404, detail="No public field profile linked to this GTIN")

    row = public[0]
    fp = row["pcf_field_profiles"]
    cy = fp.get("pcf_crop_years", {})
    field = cy.get("pcf_fields", {})
    farm = field.get("pcf_farms", {})

    return {
        "gtin": row["gtin"],
        "batch_id": row.get("batch_id"),
        "field_profile": {
            "score_total": fp.get("score_total"),
            "score_water": fp.get("score_water"),
            "score_biodiversity": fp.get("score_biodiversity"),
            "score_pesticide": fp.get("score_pesticide"),
            "method_version": fp.get("method_version"),
            "calculated_at": fp.get("calculated_at"),
        },
        "region": farm.get("region"),
        "country": farm.get("country"),
        "crop_year": cy.get("year"),
        "crop_type": cy.get("crop_type"),
    }


@app.get("/fields/{field_id}/profile")
async def get_field_profile(field_id: str, authorization: str = Header(None)):
    """Return latest field profile. Requires Bearer JWT (Supabase auth)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.split(" ", 1)[1]

    # Get latest crop year for this field
    r = await sb_get(
        "pcf_crop_years",
        params={"field_id": f"eq.{field_id}", "select": "id,year,crop_type", "order": "year.desc", "limit": "1"},
        token=token,
    )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="No crop years found for this field")

    crop_year = r.json()[0]

    # Get latest profile for this crop year
    r2 = await sb_get(
        "pcf_field_profiles",
        params={
            "crop_year_id": f"eq.{crop_year['id']}",
            "select": "*",
            "order": "calculated_at.desc",
            "limit": "1",
        },
        token=token,
    )
    if r2.status_code != 200 or not r2.json():
        raise HTTPException(status_code=404, detail="No profile calculated yet")

    profile = r2.json()[0]
    return {"field_id": field_id, "crop_year": crop_year, "profile": profile}


@app.post("/fields/{field_id}/fetch-satellite")
async def fetch_satellite(field_id: str, authorization: str = Header(None)):
    """Trigger async satellite data fetch for a field."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.split(" ", 1)[1]

    # Get field geometry
    r = await sb_get(
        "pcf_fields",
        params={"id": f"eq.{field_id}", "select": "id,geometry,name"},
        token=token,
    )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="Field not found")

    field = r.json()[0]

    # Get latest crop year
    r2 = await sb_get(
        "pcf_crop_years",
        params={"field_id": f"eq.{field_id}", "select": "id,year", "order": "year.desc", "limit": "1"},
        token=token,
    )
    if r2.status_code != 200 or not r2.json():
        raise HTTPException(status_code=404, detail="No crop year found for this field")

    crop_year = r2.json()[0]
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "field_id": field_id}

    # Run async in background
    asyncio.create_task(
        _run_satellite_job(job_id, field["geometry"], crop_year["id"], token)
    )

    return {"job_id": job_id, "status": "pending", "field_id": field_id}


@app.get("/fields/{field_id}/satellite-status/{job_id}")
async def satellite_status(field_id: str, job_id: str):
    """Check status of a satellite fetch job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/demand-signal")
async def post_demand_signal(signal: DemandSignalIn):
    """Record an anonymous demand signal (no user_id, no session_id)."""
    today = date.today()
    week = today.isocalendar()[1]
    year = today.year

    data = {
        "category": signal.category,
        "region": signal.region,
        "calendar_week": week,
        "calendar_year": year,
        "chose_better_field_profile": signal.chose_better_field_profile,
        "willingness_to_pay_pct": signal.willingness_to_pay_pct,
        "is_panel": signal.is_panel,
        "panel_code": signal.panel_code,
    }
    r = await sb_post("pcf_demand_signals", data, service=True)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail="Failed to store signal")
    return {"ok": True}


@app.get("/demand-signal/summary")
async def demand_signal_summary():
    """Aggregated summary by category+region (only when >= 20 events)."""
    r = await sb_get(
        "pcf_demand_signals",
        params={"select": "category,region,chose_better_field_profile,willingness_to_pay_pct,is_panel"},
        service=True,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch signals")

    rows = r.json()
    # Aggregate
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for row in rows:
        key = (row.get("category") or "unknown", row.get("region") or "unknown")
        groups[key].append(row)

    summary = []
    for (category, region), items in groups.items():
        n = len(items)
        if n < 20:
            continue
        chose = [i for i in items if i.get("chose_better_field_profile")]
        wtps = [i["willingness_to_pay_pct"] for i in items if i.get("willingness_to_pay_pct") is not None]
        wtp_median = sorted(wtps)[len(wtps) // 2] if wtps else None
        has_panel = any(i.get("is_panel") for i in items)
        summary.append({
            "category": category,
            "region": region,
            "n_events": n,
            "preference_rate": round(len(chose) / n, 3),
            "willingness_to_pay_pct_median": wtp_median,
            "has_panel_data": has_panel,
        })

    return {"summary": summary, "total_signals": len(rows)}


# ──────────────────────────────────────────────
# Background job
# ──────────────────────────────────────────────

async def _run_satellite_job(job_id: str, geometry: dict, crop_year_id: str, token: str):
    try:
        _jobs[job_id] = {**_jobs.get(job_id, {}), "status": "running"}

        date_to = date.today().isoformat()
        date_from = (date.today() - timedelta(days=60)).isoformat()

        ndvi_result = await fetch_ndvi_for_field(geometry, date_from, date_to)

        # Get centroid for CDI
        try:
            bbox = geojson_bbox(geometry)
            lon = (bbox[0] + bbox[2]) / 2
            lat = (bbox[1] + bbox[3]) / 2
            cdi_result = await fetch_cdi_for_point(lon, lat)
        except Exception:
            cdi_result = {"cdi": 1.0, "source": "fallback"}

        # Store indicators
        indicators_to_store = []
        best = ndvi_result.get("best", {})
        if best and not best.get("error"):
            acq = best.get("date", date.today().isoformat())
            indicators_to_store.extend([
                {
                    "crop_year_id": crop_year_id,
                    "indicator": "ndvi_mean",
                    "value": best["ndvi_mean"],
                    "unit": "index",
                    "source": "sentinel2",
                    "acquired_at": acq,
                    "method_version": "1.0",
                },
                {
                    "crop_year_id": crop_year_id,
                    "indicator": "ndvi_std",
                    "value": best["ndvi_std"],
                    "unit": "index",
                    "source": "sentinel2",
                    "acquired_at": acq,
                    "method_version": "1.0",
                },
            ])

        indicators_to_store.append({
            "crop_year_id": crop_year_id,
            "indicator": "cdi",
            "value": cdi_result.get("cdi", 1.0),
            "unit": "class",
            "source": cdi_result.get("source", "copernicus"),
            "acquired_at": date.today().isoformat(),
            "method_version": "1.0",
        })

        # Batch insert
        headers = sb_headers(use_service_key=True)
        async with httpx.AsyncClient() as client:
            for ind in indicators_to_store:
                await client.post(
                    f"{SUPABASE_URL}/rest/v1/pcf_indicator_values",
                    headers=headers,
                    json=ind,
                    timeout=10,
                )

            # Compute & store profile
            profile_scores = compute_field_profile(
                [{"indicator": i["indicator"], "value": i["value"]} for i in indicators_to_store]
            )
            profile_data = {
                "crop_year_id": crop_year_id,
                **{k: v for k, v in profile_scores.items() if k.startswith("score_") or k == "method_version"},
                "is_public": False,
            }
            await client.post(
                f"{SUPABASE_URL}/rest/v1/pcf_field_profiles",
                headers=headers,
                json=profile_data,
                timeout=10,
            )

        _jobs[job_id] = {
            "status": "done",
            "ndvi": best,
            "cdi": cdi_result,
            "indicators_stored": len(indicators_to_store),
            "profile": profile_scores,
        }

    except Exception as e:
        _jobs[job_id] = {"status": "error", "error": str(e)}
