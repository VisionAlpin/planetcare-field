FROM python:3.11-slim

# PostGIS client libs für geoalchemy2/psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc libgdal-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Gesamtes Projekt (web/ braucht die API)
COPY . .

WORKDIR /app/api

# Migrations + optionaler Seed, dann Server starten
CMD alembic upgrade head && \
    python seed_demo.py && \
    uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
