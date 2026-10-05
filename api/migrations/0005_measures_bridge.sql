-- PlanetCare Field v0.5.0: Behandlungen und Verbindung zur Verbraucher App
-- Als Alembic Migration übernehmen (op.execute) oder einmalig per psql ausführen.

-- Alte pcf_demand_events (aus 0001) hat anderes Schema — drop und neu anlegen
DROP TABLE IF EXISTS pcf_demand_events CASCADE;
DROP TABLE IF EXISTS pcf_demand_aggregates CASCADE;

-- ---------------------------------------------------------------
-- 1. Maßnahmen (Behandlungen). Falls "measures" schon existiert,
--    werden nur die fehlenden Spalten ergänzt.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pcf_measures (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id   uuid NOT NULL REFERENCES pcf_fields(id) ON DELETE CASCADE,
    day        date NOT NULL,
    type       text NOT NULL                -- 'pflanzenschutz', später auch 'duengung', 'bewaesserung'
);
ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS kind       text;              -- fungizid | herbizid | insektizid | wachstumsregler
ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS product    text;
ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS amount     double precision;
ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS unit       text;              -- l/ha | kg/ha | g/ha
ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS created_by uuid;
ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS pcf_measures_field_day_idx ON pcf_measures (field_id, day);

-- ---------------------------------------------------------------
-- 2. Lieferkette: Charge, freigegebene Schläge, Produkte (GTIN)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pcf_batches (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    label        text NOT NULL,                 -- z. B. "Weizen Ernte 2026, Lager 3"
    buyer        text NOT NULL,                 -- Genossenschaft oder Mühle
    crop         text NOT NULL,
    harvest_year integer NOT NULL,
    region_code  text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Ein Schlag zählt nur mit Freigabe des Betriebs (consent_at gesetzt, nicht widerrufen)
CREATE TABLE IF NOT EXISTS pcf_batch_fields (
    batch_id    uuid NOT NULL REFERENCES pcf_batches(id) ON DELETE CASCADE,
    field_id    uuid NOT NULL REFERENCES pcf_fields(id) ON DELETE CASCADE,
    share       double precision NOT NULL CHECK (share > 0 AND share <= 1),  -- Mengenanteil an der Charge
    consent_at  timestamptz,
    revoked_at  timestamptz,
    PRIMARY KEY (batch_id, field_id)
);

CREATE TABLE IF NOT EXISTS pcf_product_batches (
    gtin        text NOT NULL,
    batch_id    uuid NOT NULL REFERENCES pcf_batches(id) ON DELETE CASCADE,
    valid_from  date NOT NULL DEFAULT current_date,
    valid_to    date,
    PRIMARY KEY (gtin, batch_id)
);
CREATE INDEX IF NOT EXISTS pcf_product_batches_gtin_idx ON pcf_product_batches (gtin);

-- ---------------------------------------------------------------
-- 3. Nachfragesignale aus der Verbraucher App (anonym, ohne Nutzer ID)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pcf_demand_events (
    id                bigserial PRIMARY KEY,
    type              text NOT NULL,            -- scan | compare | compare_choice | filter_verified | survey_wtp
    gtin              text,
    compared_with     text[] NOT NULL DEFAULT '{}',
    verified          boolean,                  -- gewähltes Produkt hat ein Feldprofil
    compared_verified boolean[] NOT NULL DEFAULT '{}',
    category          text NOT NULL,
    region            text NOT NULL,            -- ISO 3166-2, z. B. AT-5
    week              text NOT NULL,            -- ISO Woche, z. B. 2026-W41
    panel             boolean NOT NULL DEFAULT false,
    value             double precision,         -- survey_wtp: Aufpreis in Prozent
    received_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pcf_demand_events_cat_region_week_idx ON pcf_demand_events (category, region, week);
