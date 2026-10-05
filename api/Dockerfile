FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

WORKDIR /app/api

CMD alembic upgrade head && \
    python seed_demo.py && \
    python set_demo_geometry.py && \
    uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
