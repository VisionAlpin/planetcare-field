"""db.py — psycopg2-Verbindung für measures.py und bridge.py."""
import os
import psycopg2

_DATABASE_URL = os.getenv("DATABASE_URL", "")


def _pg_url(url: str) -> str:
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    ).replace("postgresql://", "postgres://", 1)  # psycopg2 braucht postgres://


def get_conn():
    url = _pg_url(_DATABASE_URL)
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.close()
