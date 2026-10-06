"""GET /api/fields/{field_id}/overview: vollständiger Endpunkt (ersetzt den bisherigen).

Liest ausschließlich aus der Datenbank:
  - Schlag, Betrieb, Schlagliste            Tabellen fields, farms
  - Teilwerte, Verlauf, Vorjahr, Region     Tabelle score_snapshots (Nachtjob)
und bereinigt die Antwort mit finalize_overview(). Es gibt KEINE fest eingetragenen
Werte mehr. Gibt es für einen Schlag noch keine Stichtage, liefern die Teilwerte
"available": false und das Dashboard zeigt "Noch keine Daten".

Einbau in main.py (alten Overview Endpunkt vorher entfernen):
    from .overview import router as overview_router
    app.include_router(overview_router)
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional

from .overview_queries import previous_scores, regional_values, scores_and_series
from .scoring import finalize_overview

DATA_SOURCES = ["Copernicus Sentinel 2", "ERA5-Land"]

# Spaltennamen bei Bedarf anpassen
FIELD_SQL = """
SELECT f.id::text, f.name, coalesce(f.municipality, ''), f.crop, ST_AsGeoJSON(f.geom)::text,
       ST_Area(f.geom::geography) / 10000.0, f.region_code, fa.id::text, fa.name
FROM fields f JOIN farms fa ON fa.id = f.farm_id
WHERE f.id = %s AND f.farm_id = %s
"""
DEFAULT_FIELD_SQL = "SELECT id::text FROM fields WHERE farm_id = %s AND geom IS NOT NULL ORDER BY name LIMIT 1"
FIELDS_OF_FARM_SQL = "SELECT id::text, name FROM fields WHERE farm_id = %s ORDER BY name"
SEASONS_SQL = "SELECT DISTINCT season FROM score_snapshots WHERE field_id = %s ORDER BY season DESC"
COMPUTED_AT_SQL = "SELECT max(computed_at)::date FROM score_snapshots WHERE field_id = %s AND season = %s"


def resolve_field_id(conn, field_id: str, farm_id: str) -> Optional[str]:
    if field_id != "default":
        return field_id
    with conn.cursor() as cur:
        cur.execute(DEFAULT_FIELD_SQL, (farm_id,))
        r = cur.fetchone()
    return r[0] if r else None


def build_overview(conn, field_id: str, season: int, farm_id: str, today: Optional[date] = None) -> Optional[dict]:
    """None = Schlag gehört nicht zum Betrieb oder existiert nicht."""
    today = today or date.today()
    fid = resolve_field_id(conn, field_id, farm_id)
    if not fid:
        return None
    with conn.cursor() as cur:
        cur.execute(FIELD_SQL, (fid, farm_id))
        f = cur.fetchone()
        if not f:
            return None
        cur.execute(FIELDS_OF_FARM_SQL, (farm_id,))
        fields = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
        cur.execute(SEASONS_SQL, (fid,))
        seasons = sorted({int(r[0]) for r in cur.fetchall()} | {today.year}, reverse=True)
        cur.execute(COMPUTED_AT_SQL, (fid, season))
        r = cur.fetchone()
        computed_at = r[0].isoformat() if r and r[0] else None

    raw = {
        "farm": {"id": f[7], "name": f[8]},
        "field": {
            "id": f[0], "name": f[1], "municipality": f[2], "crop": f[3], "season": season,
            "geometry": json.loads(f[4]), "areaHa": round(float(f[5]), 2), "regionCode": f[6],
        },
        "seasons": seasons,
        "fields": fields,
        "hint": None,
        "methodology": {"version": "v1.0", "computedAt": computed_at, "dataSources": DATA_SOURCES},
    }
    raw["scores"], raw["series"] = scores_and_series(conn, fid, season)
    return finalize_overview(raw, previous_scores(conn, fid, season - 1), regional_values(conn, fid, season))


try:
    import fastapi  # noqa: F401
except ImportError:  # nur in Tests ohne FastAPI
    fastapi = None

router = None
if fastapi is not None:
    from fastapi import APIRouter, Depends, HTTPException, status

    from .auth import current_user
    from .db import get_conn  # ANPASSEN
    from .schemas import Overview

    router = APIRouter(tags=["Übersicht"])

    @router.get("/api/fields/{field_id}/overview", response_model=Overview)
    def get_overview(field_id: str, season: Optional[int] = None, conn=Depends(get_conn), user=Depends(current_user)):
        out = build_overview(conn, field_id, season or date.today().year, user.farm_id)
        if out is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Schlag nicht gefunden")
        return out
