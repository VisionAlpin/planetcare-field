"""v0.6.0 – users, login_tokens, sessions

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users (
        id          text PRIMARY KEY DEFAULT gen_random_uuid()::text,
        email       text NOT NULL UNIQUE,
        farm_id     text NOT NULL REFERENCES pcf_farms(id) ON DELETE CASCADE,
        name        text,
        role        text NOT NULL DEFAULT 'farmer',
        active      boolean NOT NULL DEFAULT true,
        created_at  timestamptz NOT NULL DEFAULT now(),
        last_login  timestamptz
    )""",

    """CREATE TABLE IF NOT EXISTS login_tokens (
        token_hash  text PRIMARY KEY,
        user_id     text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at  timestamptz NOT NULL DEFAULT now(),
        expires_at  timestamptz NOT NULL,
        used_at     timestamptz
    )""",
    "CREATE INDEX IF NOT EXISTS login_tokens_user_idx ON login_tokens (user_id, created_at)",

    """CREATE TABLE IF NOT EXISTS sessions (
        session_hash text PRIMARY KEY,
        user_id      text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at   timestamptz NOT NULL DEFAULT now(),
        expires_at   timestamptz NOT NULL,
        revoked_at   timestamptz,
        user_agent   text
    )""",
    "CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id)",
]


def upgrade():
    conn = op.get_bind()
    for stmt in STATEMENTS:
        conn.execute(sa.text(stmt))


def downgrade():
    conn = op.get_bind()
    for tbl in ["sessions", "login_tokens", "users"]:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
