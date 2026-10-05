"""Verbindung zur Verbraucher App PlanetCareScan (Server zu Server).

Endpunkte (ersetzen die bisherigen Platzhalter mit denselben Pfaden):
  GET  /api/products/{gtin}/field-profile   Anbauinfo für die Produktseite      (ServiceApiKey)
  POST /api/demand-events                   anonyme Nachfragesignale             (ServiceApiKey)
  GET  /api/market-signal?region=&category=  Marktsignal fürs Dashboard          (Anmeldung Landwirt)

Einbau in main.py:
    from .bridge import router as bridge_router
    app.include_router(bridge_router)
Die alten Routen mit denselben Pfaden vorher entfernen.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from statistics import median
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .scoring import is_num

MIN_EVENTS = 20          # unter dieser Zahl werden keine Werte ausgegeben (Anonymität)
SIGNAL_WEEKS = 12        # Zeitraum des Marktsignals
KEYS = ("water", "soil", "protection")

EventType = Literal["scan", "compare", "compare_choice", "filter_verified", "survey_wtp"]


class DemandEventIn(BaseModel):
    type: EventType
    gtin: Optional[str] = Field(default=None, pattern=r"^\d{8,14}$")
    comparedWith: list[str] = Field(default_factory=list, max_length=3)
    verified: Optional[bool] = Field(default=None, description="Gewähltes bzw. gescanntes Produkt hat ein Feldprofil")
    comparedVerified: list[bool] = Field(default_factory=list, max_length=3, description="Feldprofil ja/nein je Vergleichsprodukt, gleiche Reihenfolge wie comparedWith")
    category: str = Field(min_length=2, max_length=60)
    region: str = Field(pattern=r"^[A-Z]{2}-[0-9A-Z]{1,3}$", description="ISO 3166-2, z. B. AT-5")
    week: str = Field(pattern=r"^\d{4}-W\d{2}$", description="ISO Kalenderwoche, z. B. 2026-W41")
    panel: bool = False
    value: Optional[float] = Field(default=None, ge=0, le=100, description="Nur survey_wtp: Aufpreis in Prozent")

    @field_validator("comparedVerified")
    @classmethod
    def _same_len(cls, v, info):
        cw = info.data.get("comparedWith") or []
        if v and len(v) != len(cw):
            raise ValueError("comparedVerified muss gleich lang sein wie comparedWith")
        return v


class DemandEventBatch(BaseModel):
    events: list[DemandEventIn] = Field(max_length=1000)


class FieldProfile(BaseModel):
    gtin: str
    verified: bool
    profileScore: Optional[float]
    scores: dict[str, Optional[float]]
    fieldsCount: int
    region: Optional[str]
    harvestYear: int
    methodology: str = "v1.0"


class CategorySignal(BaseModel):
    category: str
    region: str
    events: int
    preferenceRate: Optional[float] = Field(description="Anteil der Wahl für das Produkt MIT Feldprofil, wenn eines der verglichenen Produkte eines hat (0 bis 1)")
    comparisons: int
    willingnessToPayMedian: Optional[float] = Field(description="Median Aufpreis in Prozent aus der Kurzumfrage")
    surveyAnswers: int
    panelShare: float
    weeks: int = SIGNAL_WEEKS


# ---------------------------------------------------------------
# Logik ohne Datenbank (testbar)
# ---------------------------------------------------------------

def weighted_profile(rows: list[tuple]) -> Optional[dict]:
    """rows: (share, water, soil, protection) je freigegebenem Schlag der Charge."""
    scores = {}
    for i, k in enumerate(KEYS, start=1):
        pairs = [(r[0], r[i]) for r in rows if is_num(r[i]) and r[0] > 0]
        w = sum(p[0] for p in pairs)
        scores[k] = round(sum(s * v for s, v in pairs) / w, 1) if w else None
    vals = [v for v in scores.values() if v is not None]
    if len(vals) < 2:
        return None
    return {"scores": scores, "profileScore": round(sum(vals) / len(vals), 1)}


def preference_rate(events: list[dict]) -> tuple[Optional[float], int]:
    """Nur Vergleiche, in denen sich die Produkte im Feldprofil unterscheiden, zählen."""
    relevant = []
    for e in events:
        if e["type"] != "compare_choice" or e.get("verified") is None:
            continue
        others = e.get("compared_verified") or []
        if not others:
            continue
        if e["verified"] and not all(others):
            relevant.append(1)
        elif not e["verified"] and any(others):
            relevant.append(0)
    if len(relevant) < MIN_EVENTS:
        return None, len(relevant)
    return round(sum(relevant) / len(relevant), 3), len(relevant)


def wtp_median(events: list[dict]) -> tuple[Optional[float], int]:
    vals = [e["value"] for e in events if e["type"] == "survey_wtp" and is_num(e.get("value"))]
    if len(vals) < MIN_EVENTS:
        return None, len(vals)
    return float(median(vals)), len(vals)


def iso_weeks_back(today: date, weeks: int) -> list[str]:
    out = []
    for i in range(weeks):
        y, w, _ = (today - timedelta(weeks=i)).isocalendar()
        out.append(f"{y}-W{w:02d}")
    return out


def build_signal(category: str, region: str, events: list[dict]) -> CategorySignal:
    rate, comps = preference_rate(events)
    wtp, answers = wtp_median(events)
    n = len(events)
    return CategorySignal(
        category=category,
        region=region,
        events=n,
        preferenceRate=rate,
        comparisons=comps,
        willingnessToPayMedian=wtp,
        surveyAnswers=answers,
        panelShare=round(sum(1 for e in events if e.get("panel")) / n, 3) if n else 0.0,
    )


# ---------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------

PROFILE_SQL = """
WITH b AS (
  SELECT pb.batch_id, bt.harvest_year, bt.region_code
  FROM pcf_product_batches pb JOIN pcf_batches bt ON bt.id = pb.batch_id
  WHERE pb.gtin = %s AND pb.valid_from <= %s AND (pb.valid_to IS NULL OR pb.valid_to >= %s)
  ORDER BY pb.valid_from DESC LIMIT 1
),
f AS (
  SELECT bf.field_id, bf.share, b.harvest_year, b.region_code
  FROM pcf_batch_fields bf JOIN b ON b.batch_id = bf.batch_id
  WHERE bf.consent_at IS NOT NULL AND bf.revoked_at IS NULL
)
SELECT f.share, s.water, s.soil, s.protection, f.harvest_year, f.region_code
FROM f
JOIN LATERAL (
  SELECT water, soil, protection FROM pcf_score_snapshots
  WHERE field_id = f.field_id AND season = f.harvest_year ORDER BY asof DESC LIMIT 1
) s ON true
"""


def field_profile(conn, gtin: str, today: Optional[date] = None) -> Optional[FieldProfile]:
    today = today or date.today()
    with conn.cursor() as cur:
        cur.execute(PROFILE_SQL, (gtin, today, today))
        rows = cur.fetchall()
    if not rows:
        return None
    prof = weighted_profile([(r[0], r[1], r[2], r[3]) for r in rows])
    if not prof:
        return None
    return FieldProfile(gtin=gtin, verified=True, profileScore=prof["profileScore"], scores=prof["scores"],
                        fieldsCount=len(rows), region=rows[0][5], harvestYear=rows[0][4])


def store_events(conn, batch: DemandEventBatch) -> int:
    import json as _json
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO pcf_demand_events (type, gtin, compared_with, verified, compared_verified, category, region, week, panel, value) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [(e.type, e.gtin, _json.dumps(e.comparedWith), e.verified,
              _json.dumps(e.comparedVerified), e.category, e.region, e.week, e.panel, e.value)
             for e in batch.events],
        )
    conn.commit()
    return len(batch.events)


def market_signal(conn, region: str, category: Optional[str], today: Optional[date] = None) -> list[CategorySignal]:
    weeks = iso_weeks_back(today or date.today(), SIGNAL_WEEKS)
    sql = ("SELECT category, type, verified, compared_verified, panel, value FROM pcf_demand_events "
           "WHERE region = %s AND week = ANY(%s)" + (" AND category = %s" if category else ""))
    params = [region, weeks] + ([category] if category else [])
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r[0], []).append({"type": r[1], "verified": r[2], "compared_verified": r[3], "panel": r[4], "value": r[5]})
    return sorted((build_signal(c, region, ev) for c, ev in by_cat.items()), key=lambda s: -s.events)


# ---------------------------------------------------------------
# Router
# ---------------------------------------------------------------

try:
    import fastapi  # noqa: F401
except ImportError:  # nur in Tests ohne FastAPI
    fastapi = None

router = None
if fastapi is not None:
    from fastapi import APIRouter, Depends, HTTPException, Query, status

    from .auth import current_user   # ANPASSEN
    from .db import get_conn         # ANPASSEN
    from .schemas import require_service_key

    router = APIRouter(tags=["Verbraucher App"])

    @router.get("/api/products/{gtin}/field-profile", response_model=FieldProfile,
                dependencies=[Depends(require_service_key)])
    def get_field_profile(gtin: str, conn=Depends(get_conn)):
        if not re.fullmatch(r"\d{8,14}", gtin):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "GTIN ungültig")
        prof = field_profile(conn, gtin)
        if prof is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Kein Feldprofil")
        return prof

    @router.post("/api/demand-events", status_code=202, dependencies=[Depends(require_service_key)])
    def post_demand_events(batch: DemandEventBatch, conn=Depends(get_conn)):
        return {"accepted": store_events(conn, batch)}

    @router.get("/api/market-signal", response_model=list[CategorySignal])
    def get_market_signal(region: str = Query(pattern=r"^[A-Z]{2}-[0-9A-Z]{1,3}$"), category: Optional[str] = None,
                          conn=Depends(get_conn), user=Depends(current_user)):
        return market_signal(conn, region, category)
