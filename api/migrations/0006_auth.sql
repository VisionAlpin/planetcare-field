-- PlanetCare Field v0.6.0: Anmeldung per E Mail Link
-- Annahme: Tabelle farms(id uuid, name text) existiert (Betriebe).

CREATE TABLE IF NOT EXISTS users (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email       text NOT NULL UNIQUE,              -- immer klein geschrieben speichern
    farm_id     uuid NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    name        text,
    role        text NOT NULL DEFAULT 'farmer',    -- farmer | advisor | admin
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_login  timestamptz
);

-- Einmal Links: nur der SHA 256 Hash wird gespeichert, nie der Link selbst
CREATE TABLE IF NOT EXISTS login_tokens (
    token_hash  text PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz
);
CREATE INDEX IF NOT EXISTS login_tokens_user_idx ON login_tokens (user_id, created_at);

CREATE TABLE IF NOT EXISTS sessions (
    session_hash text PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    revoked_at   timestamptz,
    user_agent   text
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);
