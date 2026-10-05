"""Datenbankzugriff des Nachtjobs (Postgres + PostGIS, psycopg 3).

Tabellen- und Spaltennamen stehen gesammelt hier oben. Weicht das bestehende
Schema ab, nur diese SQL Texte anpassen.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Optional

FIELDS_SQL = """
SELECT f.id::text, f.name,
       f.geom::text,
       f.season_start,
       ((f.geom->'coordinates'->0->0->>1)::float + (f.geom->'coordinates'->0->2->>1)::float) / 2,
       ((f.geom->'coordinates'->0->0->>0)::float + (f.geom->'coordinates'->0->2->>0)::float) / 2,
       COALESCE(f.area_ha, 10.0)
FROM pcf_fields f
WHERE f.geom IS NOT NULL
ORDER BY f.name
"""

# Pflanzenschutz: Tabelle pcf_indicator_values mit indicator='pesticide'
TREATMENTS_SQL = """
SELECT iv.acquired_at FROM pcf_indicator_values iv
WHERE iv.crop_year_id IN (
    SELECT cy.id FROM pcf_crop_years cy WHERE cy.field_id = %s
      AND cy.year = EXTRACT(YEAR FROM %s::date)
)
AND iv.indicator = 'pesticide'
AND iv.acquired_at BETWEEN %s AND %s
"""

UPSERT_INDICATOR_SQL = """
INSERT INTO indicator_values (field_id, day, indicator, value, quality, source)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (field_id, day, indicator) DO UPDATE
SET value = EXCLUDED.value, quality = EXCLUDED.quality, source = EXCLUDED.source, created_at = now()
"""

UPSERT_SNAPSHOT_SQL = """
INSERT INTO score_snapshots (field_id, season, asof, water, soil, protection, sources, data_dates, methodology)
VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
ON CONFLICT (field_id, season, asof) DO UPDATE
SET water = EXCLUDED.water, soil = EXCLUDED.soil, protection = EXCLUDED.protection,
    sources = EXCLUDED.sources, data_dates = EXCLUDED.data_dates,
    methodology = EXCLUDED.methodology, computed_at = now()
"""


@dataclass
class FieldRow:
    id: str
    name: str
    geometry: dict
    season_start: Optional[date]
    lat: float
    lon: float
    area_ha: float


class PostgresStore:
    def __init__(self, dsn: str | None = None):
        import psycopg  # erst hier, damit Tests ohne Treiber laufen

        self.conn = psycopg.connect(dsn or os.environ["DATABASE_URL"], autocommit=False)

    def fields(self) -> list[FieldRow]:
        with self.conn.cursor() as cur:
            cur.execute(FIELDS_SQL)
            rows = cur.fetchall()
            result = []
            for r in rows:
                geom = r[2] if isinstance(r[2], dict) else json.loads(r[2] or "{}")
                result.append(FieldRow(r[0], r[1], geom, r[3], float(r[4] or 0), float(r[5] or 0), float(r[6] or 10)))
            return result

    def treatments(self, field_id: str, start: date, end: date) -> list[date]:
        with self.conn.cursor() as cur:
            cur.execute(TREATMENTS_SQL, (field_id, start, start, end))
            return [r[0] for r in cur.fetchall()]

    def save_indicators(self, field_id: str, rows: list[tuple]) -> None:
        """rows: (day, indicator, value, quality, source)"""
        with self.conn.cursor() as cur:
            cur.executemany(UPSERT_INDICATOR_SQL, [(field_id, *r) for r in rows])

    def save_snapshot(self, field_id: str, season: int, snap, methodology: str) -> None:
        dates = {k: (v.isoformat() if v else None) for k, v in snap.data_dates.items()}
        with self.conn.cursor() as cur:
            cur.execute(
                UPSERT_SNAPSHOT_SQL,
                (field_id, season, snap.asof, snap.water, snap.soil, snap.protection, json.dumps(snap.sources), json.dumps(dates), methodology),
            )

    def start_run(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO job_runs DEFAULT VALUES RETURNING id")
            run_id = cur.fetchone()[0]
        self.conn.commit()
        return run_id

    def finish_run(self, run_id: int, status: str, ok: int, failed: int, message: str = "") -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE job_runs SET finished_at = now(), status = %s, fields_ok = %s, fields_failed = %s, message = %s WHERE id = %s",
                (status, ok, failed, message[:4000], run_id),
            )
        self.conn.commit()

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def set_geometry(self, field_id: str, geojson: dict) -> float:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE fields SET geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) WHERE id = %s "
                "RETURNING ST_Area(geom::geography) / 10000.0",
                (json.dumps(geojson), field_id),
            )
            row = cur.fetchone()
        if not row:
            raise SystemExit(f"Schlag {field_id} nicht gefunden")
        self.conn.commit()
        return float(row[0])
