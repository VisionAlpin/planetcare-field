"""Initial migration — alle Tabellen (JSON-Geometrie, kein PostGIS nötig)"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pcf_farms",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("owner_email", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("country", sa.String(2), server_default="AT"),
        sa.Column("region", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pcf_farms_owner_email", "pcf_farms", ["owner_email"])

    op.create_table(
        "pcf_fields",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("farm_id", sa.Text, sa.ForeignKey("pcf_farms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text),
        sa.Column("area_ha", sa.Numeric),
        sa.Column("geom", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "pcf_crop_years",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("field_id", sa.Text, sa.ForeignKey("pcf_fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("crop_type", sa.Text),
        sa.Column("sowing_date", sa.Date),
        sa.Column("harvest_date", sa.Date),
    )
    op.create_table(
        "pcf_indicator_values",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("crop_year_id", sa.Text, sa.ForeignKey("pcf_crop_years.id", ondelete="CASCADE"), nullable=False),
        sa.Column("indicator", sa.Text, nullable=False),
        sa.Column("value", sa.Numeric),
        sa.Column("unit", sa.Text),
        sa.Column("source", sa.Text),
        sa.Column("acquired_at", sa.Date),
        sa.Column("method_version", sa.Text, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "pcf_field_profiles",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("crop_year_id", sa.Text, sa.ForeignKey("pcf_crop_years.id"), nullable=False),
        sa.Column("score_water", sa.Numeric),
        sa.Column("score_biodiversity", sa.Numeric),
        sa.Column("score_pesticide", sa.Numeric),
        sa.Column("score_total", sa.Numeric),
        sa.Column("method_version", sa.Text, server_default="1.0"),
        sa.Column("is_public", sa.Boolean, server_default="false"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "pcf_product_links",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("gtin", sa.Text, nullable=False),
        sa.Column("field_profile_id", sa.Text, sa.ForeignKey("pcf_field_profiles.id", ondelete="CASCADE")),
        sa.Column("batch_id", sa.Text),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pcf_product_links_gtin", "pcf_product_links", ["gtin"])
    op.create_table(
        "pcf_demand_events",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("gtin", sa.Text),
        sa.Column("compared_with", sa.Text),
        sa.Column("category", sa.Text),
        sa.Column("region", sa.Text),
        sa.Column("calendar_week", sa.Text),
        sa.Column("panel", sa.Boolean, server_default="false"),
        sa.Column("willingness_to_pay", sa.Numeric),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "pcf_demand_aggregates",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("region", sa.Text, nullable=False),
        sa.Column("calendar_week", sa.Text, nullable=False),
        sa.Column("n_events", sa.Integer, server_default="0"),
        sa.Column("preference_rate", sa.Numeric),
        sa.Column("wtp_median", sa.Numeric),
        sa.Column("has_panel", sa.Boolean, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "pcf_consents",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("farm_id", sa.Text, sa.ForeignKey("pcf_farms.id", ondelete="CASCADE")),
        sa.Column("consent_type", sa.Text, nullable=False),
        sa.Column("granted", sa.Boolean, server_default="false"),
        sa.Column("granted_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    for t in [
        "pcf_consents", "pcf_demand_aggregates", "pcf_demand_events",
        "pcf_product_links", "pcf_field_profiles", "pcf_indicator_values",
        "pcf_crop_years", "pcf_fields", "pcf_farms",
    ]:
        op.drop_table(t)
