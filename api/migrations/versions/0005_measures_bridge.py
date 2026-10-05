"""v0.5.0 – measures, batches, demand_events

Revision ID: 0005
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0002"
branch_labels = None
depends_on = None

STATEMENTS = [
    # Alte Tabellen mit inkompatiblem Schema ersetzen
    "DROP TABLE IF EXISTS pcf_demand_events CASCADE",
    "DROP TABLE IF EXISTS pcf_demand_aggregates CASCADE",

    # Behandlungen
    """CREATE TABLE IF NOT EXISTS pcf_measures (
        id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        field_id   uuid NOT NULL REFERENCES pcf_fields(id) ON DELETE CASCADE,
        day        date NOT NULL,
        type       text NOT NULL
    )""",
    "ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS kind       text",
    "ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS product    text",
    "ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS amount     double precision",
    "ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS unit       text",
    "ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS created_by uuid",
    "ALTER TABLE pcf_measures ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()",
    "CREATE INDEX IF NOT EXISTS pcf_measures_field_day_idx ON pcf_measures (field_id, day)",

    # Chargen
    """CREATE TABLE IF NOT EXISTS pcf_batches (
        id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        label        text NOT NULL,
        buyer        text NOT NULL,
        crop         text NOT NULL,
        harvest_year integer NOT NULL,
        region_code  text,
        created_at   timestamptz NOT NULL DEFAULT now()
    )""",

    """CREATE TABLE IF NOT EXISTS pcf_batch_fields (
        batch_id    uuid NOT NULL REFERENCES pcf_batches(id) ON DELETE CASCADE,
        field_id    uuid NOT NULL REFERENCES pcf_fields(id) ON DELETE CASCADE,
        share       double precision NOT NULL CHECK (share > 0 AND share <= 1),
        consent_at  timestamptz,
        revoked_at  timestamptz,
        PRIMARY KEY (batch_id, field_id)
    )""",

    """CREATE TABLE IF NOT EXISTS pcf_product_batches (
        gtin        text NOT NULL,
        batch_id    uuid NOT NULL REFERENCES pcf_batches(id) ON DELETE CASCADE,
        valid_from  date NOT NULL DEFAULT current_date,
        valid_to    date,
        PRIMARY KEY (gtin, batch_id)
    )""",
    "CREATE INDEX IF NOT EXISTS pcf_product_batches_gtin_idx ON pcf_product_batches (gtin)",

    # Nachfragesignale (neu, ohne Array-Typen für Kompatibilität)
    """CREATE TABLE IF NOT EXISTS pcf_demand_events (
        id                bigserial PRIMARY KEY,
        type              text NOT NULL,
        gtin              text,
        compared_with     text NOT NULL DEFAULT '[]',
        verified          boolean,
        compared_verified text NOT NULL DEFAULT '[]',
        category          text NOT NULL,
        region            text NOT NULL,
        week              text NOT NULL,
        panel             boolean NOT NULL DEFAULT false,
        value             double precision,
        received_at       timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS pcf_demand_events_cat_region_week_idx ON pcf_demand_events (category, region, week)",
]


def upgrade():
    conn = op.get_bind()
    for stmt in STATEMENTS:
        conn.execute(sa.text(stmt))


def downgrade():
    conn = op.get_bind()
    for tbl in ["pcf_demand_events", "pcf_product_batches",
                "pcf_batch_fields", "pcf_batches", "pcf_measures"]:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
