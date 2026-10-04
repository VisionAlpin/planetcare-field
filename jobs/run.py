"""PlanetCare Field — Nachtjob (Satellit, Dürre, Scoring)
Läuft täglich 02:00 UTC auf Render (pcf-jobs).
"""

import os
import sys
import asyncio
import uuid
from datetime import date, timedelta

db_url = os.environ.get("DATABASE_URL", "")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
os.environ["DATABASE_URL"] = db_url

sys.path.insert(0, os.path.dirname(__file__) + "/../api")
from database import SessionLocal
from models import CropYear, IndicatorValue, FieldProfile, Field, Farm
from satellite import fetch_ndvi_for_field, fetch_cdi_for_point, geojson_bbox
from scoring import compute_field_profile

from geoalchemy2.shape import to_shape
import json


async def process_crop_year(db, cy: CropYear):
    field = cy.field
    print(f"  Verarbeite: {field.name} ({cy.year})")

    # Geometrie aus DB holen
    shape = to_shape(field.geom)
    geojson = json.loads(shape.__geo_interface__.__repr__()) if hasattr(shape, '__geo_interface__') else {}

    # Einfacheres GeoJSON aus WKT
    try:
        geojson = {"type": "Polygon", "coordinates": [list(shape.exterior.coords)]}
    except Exception:
        print(f"    Geometrie-Fehler, überspringe {field.name}")
        return

    date_to = date.today().isoformat()
    date_from = (date.today() - timedelta(days=60)).isoformat()

    # 1. Sentinel-2 NDVI
    print(f"    Lade Sentinel-2 NDVI...")
    try:
        ndvi_result = await fetch_ndvi_for_field(geojson, date_from, date_to)
        best = ndvi_result.get("best", {})
    except Exception as e:
        print(f"    NDVI-Fehler: {e}")
        best = {}

    # 2. CDI (Dürre)
    print(f"    Lade CDI...")
    try:
        bbox = geojson_bbox(geojson)
        lon = (bbox[0] + bbox[2]) / 2
        lat = (bbox[1] + bbox[3]) / 2
        cdi_result = await fetch_cdi_for_point(lon, lat)
    except Exception as e:
        print(f"    CDI-Fehler: {e}")
        cdi_result = {"cdi": 1.0, "source": "fallback"}

    # 3. Indikatoren speichern
    today = date.today()
    new_indicators = []

    if best and not best.get("error"):
        acq = best.get("date", today.isoformat())
        for ind_name, val in [("ndvi_mean", best.get("ndvi_mean")), ("ndvi_std", best.get("ndvi_std"))]:
            if val is not None:
                ind = IndicatorValue(
                    id=str(uuid.uuid4()),
                    crop_year_id=str(cy.id),
                    indicator=ind_name,
                    value=val,
                    unit="index",
                    source="sentinel2",
                    acquired_at=acq,
                    method_version="1.0",
                )
                db.add(ind)
                new_indicators.append({"indicator": ind_name, "value": float(val)})

    cdi_ind = IndicatorValue(
        id=str(uuid.uuid4()),
        crop_year_id=str(cy.id),
        indicator="cdi",
        value=cdi_result.get("cdi", 1.0),
        unit="class",
        source=cdi_result.get("source", "copernicus_gdo"),
        acquired_at=today,
        method_version="1.0",
    )
    db.add(cdi_ind)
    new_indicators.append({"indicator": "cdi", "value": float(cdi_result.get("cdi", 1.0))})

    # Bestehende Pestizid-Indikatoren einbeziehen
    existing = db.query(IndicatorValue).filter(
        IndicatorValue.crop_year_id == str(cy.id),
        IndicatorValue.indicator == "pesticide",
    ).all()
    new_indicators += [{"indicator": i.indicator, "value": float(i.value)} for i in existing]

    # 4. Scoring
    scores = compute_field_profile(new_indicators)
    print(f"    Scores: {scores}")

    profile = FieldProfile(
        id=str(uuid.uuid4()),
        crop_year_id=str(cy.id),
        score_water=scores.get("score_water"),
        score_biodiversity=scores.get("score_biodiversity"),
        score_pesticide=scores.get("score_pesticide"),
        score_total=scores.get("score_total"),
        method_version=scores.get("method_version", "1.0"),
        is_public=False,
    )
    db.add(profile)
    db.commit()
    print(f"    Profil gespeichert.")


async def main():
    print(f"PlanetCare Field Nachtjob — {date.today()}")
    db = SessionLocal()
    try:
        # Alle aktiven Anbaujahre (laufendes + letztes Jahr)
        current_year = date.today().year
        crop_years = (
            db.query(CropYear)
            .join(Field)
            .join(Farm)
            .filter(CropYear.year >= current_year - 1)
            .all()
        )
        print(f"Verarbeite {len(crop_years)} Anbaujahre...")
        for cy in crop_years:
            await process_crop_year(db, cy)
    finally:
        db.close()
    print("Nachtjob abgeschlossen.")


if __name__ == "__main__":
    asyncio.run(main())
