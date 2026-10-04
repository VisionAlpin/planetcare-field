# PlanetCare Field

**PlanetCare Field** is an open-source sustainability dashboard module for farmers. It shows how sustainably a farm is operated — based on satellite Earth Observation data (Sentinel-2 NDVI, Copernicus CDI) and optional manual inputs — and what the market is willing to pay for sustainable produce. The module links field-level sustainability profiles to product GTINs, enabling transparent supply chains from field to consumer.

## Prerequisites

- Python 3.11+
- Docker & Docker Compose
- A Supabase account (free tier works) — [supabase.com](https://supabase.com)

## Quickstart

```bash
# 1. Clone and set up environment
git clone <repo-url>
cd PlanetCareField
cp .env.example .env
# Edit .env — fill in your SUPABASE_SERVICE_KEY

# 2. Apply database schema
# Open https://supabase.com/dashboard/project/bssctgrkzdoirorpkfds/sql
# and paste the contents of db/schema.sql

# 3. Start services
docker-compose up

# API:      http://localhost:8000
# Frontend: http://localhost:3000
# Demo:     http://localhost:3000/?demo=1
```

## API Documentation

See [openapi.yaml](./openapi.yaml) for the full OpenAPI v3 specification.

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/products/{gtin}/field-profile` | Public profile by GTIN |
| GET | `/fields/{id}/profile` | Field profile (authenticated) |
| POST | `/fields/{id}/fetch-satellite` | Trigger Sentinel-2 NDVI fetch |
| POST | `/demand-signal` | Record anonymous preference signal |
| GET | `/demand-signal/summary` | Aggregated market demand summary |

## Architecture

```
frontend/   Vanilla HTML/CSS/JS PWA (no build step)
api/        Python FastAPI + httpx → Supabase REST
db/         PostgreSQL schema (Supabase, RLS-enabled)
```

Satellite data is fetched from the [Element84 Earth Search STAC API](https://earth-search.aws.element84.com/v1) (free, no account required). Drought data from [Copernicus GDO](https://drought.emergency.copernicus.eu/).

## NOSTRADAMUS / Horizon Europe Context

This module serves as TRL-4 demonstrator for the **NOSTRADAMUS** project under Horizon Europe. It provides a reproducible, open-source implementation of field-level sustainability scoring linked to market demand signals — a core component of the NOSTRADAMUS value chain transparency framework. The scoring methodology (NDVI-based water and biodiversity indicators + CDI drought index) follows the methodological requirements outlined in the NOSTRADAMUS work packages.

## License

Apache 2.0 — see [LICENSE](./LICENSE)

## Contributing

Issues and PRs welcome. Please keep the no-build-step constraint for the frontend and use only open/free data sources.
