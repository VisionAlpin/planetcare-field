"""Seed-Skript: Musterbetrieb Flachgau mit 2 Schlägen und Demo-Profilen"""

import os
import sys
import uuid
from datetime import date

# Render postgres:// → postgresql://
db_url = os.environ.get("DATABASE_URL", "")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
os.environ["DATABASE_URL"] = db_url

from database import SessionLocal
from models import (
    Farm, Field, CropYear, IndicatorValue, FieldProfile, ProductLink
)

DEMO_EMAIL = "demo@planetcarescan.at"

# Schlag Nord — Polygon um Oberndorf, Salzburg (vereinfacht)
GEOM_NORD = [[13.08, 47.92], [13.09, 47.92], [13.09, 47.91], [13.08, 47.91], [13.08, 47.92]]
GEOM_SUED = [[13.10, 47.90], [13.11, 47.90], [13.11, 47.89], [13.10, 47.89], [13.10, 47.90]]


def run():
    db = SessionLocal()
    try:
        # Idempotent: erst löschen falls schon vorhanden
        existing = db.query(Farm).filter(Farm.name == "Musterbetrieb Flachgau").first()
        if existing:
            print("Demo-Daten bereits vorhanden, überspringe.")
            return

        farm = Farm(
            id=str(uuid.uuid4()),
            owner_email=DEMO_EMAIL,
            name="Musterbetrieb Flachgau",
            country="AT",
            region="Salzburg-Umgebung",
        )
        db.add(farm)
        db.flush()

        def make_field(name, coords, crop, area):
            f = Field(
                id=str(uuid.uuid4()),
                farm_id=farm.id,
                name=name,
                area_ha=area,
                geom={"type": "Polygon", "coordinates": [coords]},
            )
            db.add(f)
            db.flush()

            for year, scores in [(2025, (74, 52, 79)), (2026, (78, 57, 82))]:
                cy = CropYear(
                    id=str(uuid.uuid4()),
                    field_id=f.id,
                    year=year,
                    crop_type=crop,
                    sowing_date=date(year - 1, 10, 5),
                    harvest_date=date(year, 7, 20),
                )
                db.add(cy)
                db.flush()

                # Indikatoren
                indicators = [
                    ("ndvi_mean", 0.62 if year == 2025 else 0.68, "index", "sentinel2", date(year, 7, 1)),
                    ("ndvi_std",  0.11 if year == 2025 else 0.14, "index", "sentinel2", date(year, 7, 1)),
                    ("cdi",       1.2  if year == 2025 else 0.8,  "class", "copernicus_gdo", date(year, 7, 1)),
                ]
                for ind, val, unit, src, acq in indicators:
                    db.add(IndicatorValue(
                        id=str(uuid.uuid4()),
                        crop_year_id=cy.id,
                        indicator=ind, value=val, unit=unit,
                        source=src, acquired_at=acq,
                    ))

                w, b, p = scores
                total = round((w + b + p) / 3)
                profile = FieldProfile(
                    id=str(uuid.uuid4()),
                    crop_year_id=cy.id,
                    score_water=w,
                    score_biodiversity=b,
                    score_pesticide=p,
                    score_total=total,
                    method_version="1.0",
                    is_public=(year == 2026),
                )
                db.add(profile)
                db.flush()

                # Demo GTIN-Verknüpfung für 2026
                if year == 2026 and name == "Schlag Nord":
                    db.add(ProductLink(
                        id=str(uuid.uuid4()),
                        gtin="9001234567890",
                        field_profile_id=profile.id,
                        batch_id="DEMO-2026-001",
                    ))

        make_field("Schlag Nord", GEOM_NORD, "Winterweizen", 12.4)
        make_field("Schlag Süd",  GEOM_SUED, "Sommergerste",  8.7)

        db.commit()
        print("Demo-Daten eingespielt: Musterbetrieb Flachgau, 2 Schläge, Saisons 2025 + 2026.")
    except Exception as e:
        db.rollback()
        print(f"Fehler: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
