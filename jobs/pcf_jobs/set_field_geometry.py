"""Echten Schlagumriss setzen (ersetzt das Platzhalter Rechteck).

1. Umriss zeichnen auf https://geojson.io (Polygon um den Schlag, Satellitenansicht)
   oder aus INVEKOS übernehmen. Als Datei speichern, z. B. schlag-nord.geojson
2. Aufruf (Render Shell des Dienstes pcf-api oder lokal mit DATABASE_URL):
   python -m pcf_jobs.set_field_geometry <field_id> schlag-nord.geojson

Prüft: genau ein Polygon, Koordinaten in Österreich/Deutschland/Schweiz,
Fläche zwischen 0,5 und 100 ha.
"""

from __future__ import annotations

import json
import sys


def extract_polygon(data: dict) -> dict:
    if data.get("type") == "FeatureCollection":
        feats = [f for f in data.get("features", []) if (f.get("geometry") or {}).get("type") == "Polygon"]
        if len(feats) != 1:
            raise SystemExit(f"Erwartet genau ein Polygon, gefunden: {len(feats)}")
        return feats[0]["geometry"]
    if data.get("type") == "Feature":
        return extract_polygon(data["geometry"])
    if data.get("type") == "Polygon":
        return data
    raise SystemExit("Keine Polygon Geometrie gefunden")


def check_bounds(poly: dict) -> None:
    for lon, lat, *_ in poly["coordinates"][0]:
        if not (5.5 <= lon <= 17.5 and 45.5 <= lat <= 55.5):
            raise SystemExit(f"Koordinate außerhalb DACH: {lon}, {lat} (Reihenfolge lon, lat?)")


def main(argv=None) -> None:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        raise SystemExit(__doc__)
    field_id, path = argv
    with open(path, encoding="utf-8") as f:
        poly = extract_polygon(json.load(f))
    check_bounds(poly)

    from .store import PostgresStore

    area = PostgresStore().set_geometry(field_id, poly)
    if not (0.5 <= area <= 100):
        print(f"WARNUNG: Fläche {area:.1f} ha wirkt unplausibel. Bitte Umriss prüfen.")
    print(f"Umriss gespeichert. Fläche: {area:.1f} ha")


if __name__ == "__main__":
    main()
