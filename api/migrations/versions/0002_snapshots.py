"""Migration 0002 — score_snapshots, indicator_values, job_runs + region_code/season_start auf pcf_fields"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # Neue Spalten auf pcf_fields
    op.add_column("pcf_fields", sa.Column("region_code", sa.Text))
    op.add_column("pcf_fields", sa.Column("season_start", sa.Date))

    # Rohdaten je Tag (NDVI, Temperatur, Niederschlag, …)
    op.create_table(
        "indicator_values",
        sa.Column("field_id", sa.Text, sa.ForeignKey("pcf_fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("indicator", sa.Text, nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("quality", sa.Float),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("field_id", "day", "indicator"),
    )

    # Score-Snapshots je Stichtag (~10 Tage)
    op.create_table(
        "score_snapshots",
        sa.Column("field_id", sa.Text, sa.ForeignKey("pcf_fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season", sa.Integer, nullable=False),
        sa.Column("asof", sa.Date, nullable=False),
        sa.Column("water", sa.Float),
        sa.Column("soil", sa.Float),
        sa.Column("protection", sa.Float),
        sa.Column("sources", JSONB, server_default="'{}'::jsonb"),
        sa.Column("data_dates", JSONB, server_default="'{}'::jsonb"),
        sa.Column("methodology", sa.Text, server_default="v1.0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("field_id", "season", "asof"),
    )
    op.create_index("score_snapshots_season_idx", "score_snapshots", ["season", "asof"])

    # Job-Protokoll
    op.create_table(
        "job_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text, server_default="running"),
        sa.Column("fields_ok", sa.Integer, server_default="0"),
        sa.Column("fields_failed", sa.Integer, server_default="0"),
        sa.Column("message", sa.Text),
    )


def downgrade():
    op.drop_table("job_runs")
    op.drop_table("score_snapshots")
    op.drop_table("indicator_values")
    op.drop_column("pcf_fields", "season_start")
    op.drop_column("pcf_fields", "region_code")
