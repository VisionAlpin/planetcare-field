# PlanetCare Field

**PlanetCare Field** ist ein offenes Nachhaltigkeits-Dashboard für Landwirte. Es zeigt, wie nachhaltig ein Betrieb wirtschaftet — auf Basis von Satellitendaten (Sentinel-2 NDVI, Copernicus CDI) und optionalen manuellen Eingaben — und verknüpft Schlagprofile mit Produkt-GTINs für transparente Lieferketten.

TRL-4-Demonstrator für das **NOSTRADAMUS**-Projekt (Horizon Europe).

## Schnellstart (lokal)

```bash
# 1. Umgebung vorbereiten
cp .env.example .env
# .env editieren: DATABASE_URL eintragen

# 2. Dienste starten
docker compose up

# API:   http://localhost:8000
# Demo:  http://localhost:8000/demo
# Docs:  http://localhost:8000/docs
```

## Struktur

```
api/        FastAPI + SQLAlchemy, liefert API und Frontend aus
  main.py       Endpunkte
  models.py     Tabellen
  scoring.py    Feldprofil-Berechnung
  satellite.py  Sentinel-2 + CDI Abruf
  migrations/   Alembic-Migrationen
  seed_demo.py  Demo-Daten (Musterbetrieb Flachgau)
jobs/       Nachtjob (Satellit, Dürre, Scoring)
web/        Frontend (Vanilla HTML/CSS/JS, kein Build-Step)
docs/       OpenAPI v3 Beschreibung
render.yaml Render Blueprint (Infrastruktur as Code)
```

## API

| Methode | Pfad | Wer | Schutz |
|---------|------|-----|--------|
| GET | `/health` | Render | offen |
| GET | `/api/fields/{id}/overview?season=` | Dashboard | Bearer Token |
| GET | `/api/fields` | Dashboard | Bearer Token |
| GET | `/api/products/{gtin}/field-profile` | PlanetCareScan Server | SERVICE_API_KEY |
| POST | `/api/demand-events` | PlanetCareScan Server | SERVICE_API_KEY |
| GET | `/api/market-signal` | Dashboard | Bearer Token |
| GET | `/demo` | Gutachter, Partner | offen (nur Demo-Daten) |

Vollständige Beschreibung: `/docs` oder `docs/openapi.yaml`

## Satellitendaten

- NDVI: [Element84 Earth Search STAC API](https://earth-search.aws.element84.com/v1) (kostenlos)
- CDI: [Copernicus GDO](https://drought.emergency.copernicus.eu/)
- ERA5: Copernicus Climate Data Store (kostenloses Konto nötig)

## Lizenz

Apache 2.0
