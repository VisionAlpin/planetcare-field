"""v0.5.0 – measures, batches, demand_events

Revision ID: 0005
Revises: 0002
"""
from alembic import op

revision = "0005"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    import os
    sql_path = os.path.join(os.path.dirname(__file__), "..", "0005_measures_bridge.sql")
    sql = open(sql_path).read()
    op.execute(sql)


def downgrade():
    op.execute("DROP TABLE IF EXISTS pcf_demand_events CASCADE")
    op.execute("DROP TABLE IF EXISTS pcf_product_batches CASCADE")
    op.execute("DROP TABLE IF EXISTS pcf_batch_fields CASCADE")
    op.execute("DROP TABLE IF EXISTS pcf_batches CASCADE")
    op.execute("DROP TABLE IF EXISTS pcf_measures CASCADE")
