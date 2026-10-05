"""db.py — psycopg3-Verbindung für measures.py und bridge.py.

Liefert eine Raw-psycopg-Verbindung (kein SQLAlchemy),
weil measures.py und bridge.py direkt SQL ausführen.
"""
import os
import psycopg

_DATABASE_URL = os.getenv("DATABASE_URL", "")


def _pg_url(url: str) -> str:
    """Render liefert postgres://, psycopg3 braucht postgresql://"""
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )


def get_conn():
    url = _pg_url(_DATABASE_URL)
    conn = psycopg.connect(url, autocommit=False)
    try:
        yield conn
    finally:
        conn.close()
