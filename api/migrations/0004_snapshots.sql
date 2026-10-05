-- PlanetCare Field v0.4.0: Tabellen für den Nachtjob
-- Als Alembic Migration übernehmen (op.execute) oder einmalig per psql ausführen.
-- Annahme: Es gibt eine Tabelle fields(id uuid, farm_id uuid, name, crop, region_code, geom geometry(Polygon,4326)).
-- Abweichende Namen bitte in jobs/pcf_jobs/store.py (FIELDS_SQL) und api/app/overview_queries.py anpassen.

ALTER TABLE fields ADD COLUMN IF NOT EXISTS region_code text;      -- z. B. 'AT-5' oder Bezirkscode
ALTER TABLE fields ADD COLUMN IF NOT EXISTS season_start date;     -- optional, sonst 1. März

-- Rohwerte (z. B. NDVI je Aufnahmetag), für Nachvollziehbarkeit und spätere Neuberechnung
CREATE TABLE IF NOT EXISTS indicator_values (
    field_id    uuid        NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    day         date        NOT NULL,
    indicator   text        NOT NULL,          -- 'ndvi', 't_mean', 'precip', 'rh'
    value       double precision NOT NULL,
    quality     double precision,              -- z. B. Anteil wolkenfreier Pixel
    source      text        NOT NULL,          -- 'sentinel2', 'era5'
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (field_id, day, indicator)
);

-- Teilwerte je Stichtag (alle 10 Tage + heute): Grundlage für Verlauf, Vorjahr und Region
CREATE TABLE IF NOT EXISTS score_snapshots (
    field_id     uuid        NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    season       integer     NOT NULL,
    asof         date        NOT NULL,
    water        double precision,
    soil         double precision,
    protection   double precision,
    sources      jsonb       NOT NULL DEFAULT '{}'::jsonb,   -- {"water": "sentinel2_era5", ...}
    data_dates   jsonb       NOT NULL DEFAULT '{}'::jsonb,   -- letzter Messtag je Teilwert
    methodology  text        NOT NULL DEFAULT 'v1.0',
    computed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (field_id, season, asof)
);
CREATE INDEX IF NOT EXISTS score_snapshots_season_idx ON score_snapshots (season, asof);

-- Protokoll der Läufe, für /health und Fehlersuche
CREATE TABLE IF NOT EXISTS job_runs (
    id           bigserial PRIMARY KEY,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    status       text        NOT NULL DEFAULT 'running',  -- running | ok | partial | failed
    fields_ok    integer     NOT NULL DEFAULT 0,
    fields_failed integer    NOT NULL DEFAULT 0,
    message      text
);
