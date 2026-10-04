-- PlanetCare Field — Database Schema v1.0
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/bssctgrkzdoirorpkfds/sql

-- Enable pgcrypto for gen_random_bytes
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- TABLES
-- ============================================================

-- Betriebe (Farms)
CREATE TABLE IF NOT EXISTS pcf_farms (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id  uuid REFERENCES auth.users(id),
  name           text NOT NULL,
  country        char(2) DEFAULT 'AT',
  region         text,
  created_at     timestamptz DEFAULT now()
);

-- Schläge (Fields) mit GeoJSON-Geometrie
CREATE TABLE IF NOT EXISTS pcf_fields (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farm_id     uuid REFERENCES pcf_farms(id) ON DELETE CASCADE,
  name        text,
  area_ha     numeric,
  geometry    jsonb NOT NULL,  -- GeoJSON Feature
  crop_type   text,            -- z.B. 'winter_wheat', 'maize'
  created_at  timestamptz DEFAULT now()
);

-- Anbaujahre pro Schlag
CREATE TABLE IF NOT EXISTS pcf_crop_years (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  field_id      uuid REFERENCES pcf_fields(id) ON DELETE CASCADE,
  year          int NOT NULL,
  crop_type     text,
  sowing_date   date,
  harvest_date  date,
  notes         text
);

-- Indikatorwerte (Wasser, Biodiversität, Pflanzenschutz + EO-Daten)
CREATE TABLE IF NOT EXISTS pcf_indicator_values (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  crop_year_id     uuid REFERENCES pcf_crop_years(id) ON DELETE CASCADE,
  indicator        text NOT NULL,  -- 'ndvi_mean','ndvi_std','cdi','water_use','biodiversity','pesticide'
  value            numeric,
  unit             text,
  source           text,           -- 'sentinel2','manual','eodag'
  acquired_at      date,
  method_version   text DEFAULT '1.0',
  created_at       timestamptz DEFAULT now()
);

-- Feldprofile (berechnete Scores)
CREATE TABLE IF NOT EXISTS pcf_field_profiles (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  crop_year_id        uuid REFERENCES pcf_crop_years(id),
  score_water         numeric,
  score_biodiversity  numeric,
  score_pesticide     numeric,
  score_total         numeric,
  method_version      text DEFAULT '1.0',
  is_public           boolean DEFAULT false,
  share_token         text UNIQUE DEFAULT encode(gen_random_bytes(12), 'hex'),
  calculated_at       timestamptz DEFAULT now()
);

-- Verknüpfung Feldprofil → Produkt (via GTIN)
CREATE TABLE IF NOT EXISTS pcf_product_links (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  field_profile_id  uuid REFERENCES pcf_field_profiles(id),
  gtin              text NOT NULL,
  batch_id          text,
  linked_at         timestamptz DEFAULT now()
);

-- Anonyme Nachfragesignale (Opt-in, keine personenbezogenen Daten)
CREATE TABLE IF NOT EXISTS pcf_demand_signals (
  id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  category                  text,
  region                    text,           -- nur grob, z.B. 'AT', 'DE-BY'
  calendar_week             int,
  calendar_year             int,
  chose_better_field_profile boolean,
  willingness_to_pay_pct    numeric,        -- Median aus Kurzumfrage
  is_panel                  boolean DEFAULT false,
  panel_code                text,
  created_at                timestamptz DEFAULT now()
  -- KEIN user_id, KEIN session_id — Privacy by Design
);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

ALTER TABLE pcf_farms            ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcf_fields           ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcf_crop_years       ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcf_indicator_values ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcf_field_profiles   ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcf_product_links    ENABLE ROW LEVEL SECURITY;
ALTER TABLE pcf_demand_signals   ENABLE ROW LEVEL SECURITY;

-- pcf_farms: owner can read/write
CREATE POLICY "farms_owner_all" ON pcf_farms
  FOR ALL USING (auth.uid() = owner_user_id);

-- pcf_fields: accessible via farm owner
CREATE POLICY "fields_owner_all" ON pcf_fields
  FOR ALL USING (
    farm_id IN (SELECT id FROM pcf_farms WHERE owner_user_id = auth.uid())
  );

-- pcf_crop_years: accessible via farm owner
CREATE POLICY "crop_years_owner_all" ON pcf_crop_years
  FOR ALL USING (
    field_id IN (
      SELECT f.id FROM pcf_fields f
      JOIN pcf_farms fa ON fa.id = f.farm_id
      WHERE fa.owner_user_id = auth.uid()
    )
  );

-- pcf_indicator_values: accessible via farm owner
CREATE POLICY "indicators_owner_all" ON pcf_indicator_values
  FOR ALL USING (
    crop_year_id IN (
      SELECT cy.id FROM pcf_crop_years cy
      JOIN pcf_fields f ON f.id = cy.field_id
      JOIN pcf_farms fa ON fa.id = f.farm_id
      WHERE fa.owner_user_id = auth.uid()
    )
  );

-- pcf_field_profiles: owner access via crop_year
CREATE POLICY "profiles_owner_all" ON pcf_field_profiles
  FOR ALL USING (
    crop_year_id IN (
      SELECT cy.id FROM pcf_crop_years cy
      JOIN pcf_fields f ON f.id = cy.field_id
      JOIN pcf_farms fa ON fa.id = f.farm_id
      WHERE fa.owner_user_id = auth.uid()
    )
  );

-- pcf_field_profiles: public profiles readable by everyone
CREATE POLICY "profiles_public_read" ON pcf_field_profiles
  FOR SELECT USING (is_public = true);

-- pcf_product_links: readable if profile is public
CREATE POLICY "product_links_public_read" ON pcf_product_links
  FOR SELECT USING (
    field_profile_id IN (SELECT id FROM pcf_field_profiles WHERE is_public = true)
  );

-- pcf_product_links: owner write
CREATE POLICY "product_links_owner_write" ON pcf_product_links
  FOR ALL USING (
    field_profile_id IN (
      SELECT fp.id FROM pcf_field_profiles fp
      JOIN pcf_crop_years cy ON cy.id = fp.crop_year_id
      JOIN pcf_fields f ON f.id = cy.field_id
      JOIN pcf_farms fa ON fa.id = f.farm_id
      WHERE fa.owner_user_id = auth.uid()
    )
  );

-- pcf_demand_signals: anyone can INSERT (anonymous opt-in)
CREATE POLICY "demand_signals_anon_insert" ON pcf_demand_signals
  FOR INSERT WITH CHECK (true);

-- pcf_demand_signals: SELECT only via service_role (no policy = blocked for anon/auth)
-- service_role bypasses RLS by default
