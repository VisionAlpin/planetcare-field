"""Nachtjob: Satelliten und Wetterdaten laden, Teilwerte je Stichtag berechnen, speichern.

Aufruf (Render Cron, täglich 02:00 UTC):
    python -m pcf_jobs.run_nightly
Vorsaison nachrechnen (einmalig, für "zum Vorjahr"):
    python -m pcf_jobs.run_nightly --season 2025
Ohne Speichern testen:
    python -m pcf_jobs.run_nightly --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from datetime import date

from .cdse import CdseClient
from .era5 import fetch_daily_weather
from .indicators import compute_snapshot, snapshot_dates

METHODOLOGY = "v1.0"
log = logging.getLogger("pcf_jobs")


def season_window(season: int, today: date, season_start: date | None = None) -> tuple[date, date, date]:
    """(Saisonbeginn, erster Stichtag, letzter Stichtag). Getreide: 1. März bis 31. Oktober."""
    start = season_start or date(season, 3, 1)
    first = date(season, 4, 1)
    end = min(today, date(season, 10, 31))
    return start, first, end


def process_field(field, season: int, today: date, store, cdse, weather_fn, dry_run: bool = False) -> int:
    """Gibt die Anzahl gespeicherter Stichtage zurück."""
    if field.area_ha > 100:
        raise ValueError(f"Fläche {field.area_ha:.1f} ha unplausibel, Umriss prüfen")
    start, first, end = season_window(season, today, field.season_start)
    if end < first:
        return 0

    ndvi = cdse.ndvi_series(field.geometry, start, end)
    weather = weather_fn(field.lat, field.lon, start, end)
    treatments = store.treatments(field.id, start, end) if store else []
    log.info("%s: %d NDVI Aufnahmen, %d Wettertage, %d Behandlungen", field.name, len(ndvi), len(weather), len(treatments))

    snaps = [compute_snapshot(d, start, ndvi, weather, treatments) for d in snapshot_dates(first, end)]
    if dry_run:
        for s in snaps:
            log.info("  %s  Wasser %s  Boden %s  Pflanzenschutz %s", s.asof, _r(s.water), _r(s.soil), _r(s.protection))
        return len(snaps)

    store.save_indicators(
        field.id,
        [(o.day, "ndvi", o.mean, o.valid_share, "sentinel2") for o in ndvi]
        + [(w.day, "t_mean", w.t_mean_c, None, "era5") for w in weather]
        + [(w.day, "precip", w.precip_mm, None, "era5") for w in weather],
    )
    for s in snaps:
        store.save_snapshot(field.id, season, s, METHODOLOGY)
    store.commit()
    return len(snaps)


def _r(v):
    return "–" if v is None else round(v)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--season", type=int, default=date.today().year)
    p.add_argument("--field", help="nur diesen Schlag rechnen (ID)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from .store import PostgresStore

    store = PostgresStore()
    if not args.dry_run:
        n = store.close_stale_runs()
        if n:
            log.warning("%d hängende Läufe als 'failed' markiert", n)
    run_id = None if args.dry_run else store.start_run()
    ok = failed = 0
    errors: list[str] = []
    status = "failed"
    try:
        cdse = CdseClient()
        fields = [f for f in store.fields() if not args.field or f.id == args.field]
        if not fields:
            errors.append("Keine Schläge mit Geometrie gefunden")
        for f in fields:
            try:
                n = process_field(f, args.season, date.today(), store, cdse, fetch_daily_weather, args.dry_run)
                log.info("%s: %d Stichtage", f.name, n)
                ok += 1
            except Exception as e:  # ein Schlag darf die anderen nicht aufhalten
                store.rollback()
                failed += 1
                errors.append(f"{f.name}: {e}")
                log.error("%s fehlgeschlagen: %s\n%s", f.name, e, traceback.format_exc())
        status = "ok" if ok and not failed else ("partial" if ok else "failed")
    except Exception as e:  # z. B. Zugangsdaten fehlen, Datenbank weg
        errors.append(f"Abbruch: {e}")
        log.error("Abbruch: %s\n%s", e, traceback.format_exc())
    finally:
        # Der Lauf wird IMMER abgeschlossen, auch bei Abbruch (sonst bleibt er auf "running")
        if run_id:
            try:
                store.rollback()
                store.finish_run(run_id, status, ok, failed, "\n".join(errors))
            except Exception as e:  # noqa: BLE001
                log.error("Lauf konnte nicht abgeschlossen werden: %s", e)
    log.info("Fertig: %s (%d ok, %d fehlgeschlagen)", status, ok, failed)
    return 0 if status != "failed" else 1  # Exit Code 1 -> Render meldet den Fehler per E Mail


if __name__ == "__main__":
    sys.exit(main())
