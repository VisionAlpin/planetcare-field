"""Setzt realistische GeoJSON-Geometrien für die Demo-Schläge.
Einmalig ausführen: python set_demo_geometry.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from database import SessionLocal
from models import Field

# Schlag Nord: Winterweizen, ~12 ha, Gemeinde Oberndorf bei Salzburg
GEOM_NORD = {
    "type": "Polygon",
    "coordinates": [[
        [13.0812, 47.9318],
        [13.0843, 47.9324],
        [13.0866, 47.9319],
        [13.0872, 47.9308],
        [13.0861, 47.9297],
        [13.0839, 47.9293],
        [13.0819, 47.9299],
        [13.0808, 47.9310],
        [13.0812, 47.9318]
    ]]
}

# Schlag Süd: Sommergerste, ~8 ha, etwas weiter südlich
GEOM_SUED = {
    "type": "Polygon",
    "coordinates": [[
        [13.0891, 47.9241],
        [13.0918, 47.9247],
        [13.0934, 47.9241],
        [13.0936, 47.9231],
        [13.0921, 47.9223],
        [13.0898, 47.9224],
        [13.0884, 47.9232],
        [13.0891, 47.9241]
    ]]
}

FIELD_ID_NORD = "ebe79a27-b557-45e8-bbcf-aa6ba5562f0f"
FIELD_ID_SUED = "58517853-d5c5-4356-8642-8d0c0281b094"


def calc_area_ha(coords):
    import math
    ring = coords[0]
    lat0 = sum(p[1] for p in ring) / len(ring) * math.pi / 180
    R = 6371008.8
    pts = [(p[0] * math.pi / 180 * R * math.cos(lat0), p[1] * math.pi / 180 * R) for p in ring]
    area = 0
    for i in range(len(pts) - 1):
        area += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    return round(abs(area) / 2 / 10000, 1)


db = SessionLocal()
try:
    for field_id, geom, name in [
        (FIELD_ID_NORD, GEOM_NORD, "Schlag Nord"),
        (FIELD_ID_SUED, GEOM_SUED, "Schlag Süd"),
    ]:
        field = db.query(Field).filter(Field.id == field_id).first()
        if field:
            field.geom = geom
            field.area_ha = calc_area_ha(geom["coordinates"])
            try:
                field.region_code = "AT-5"
            except Exception:
                pass
            print(f"  {name}: {field.area_ha} ha gesetzt, region_code=AT-5")
        else:
            print(f"  {name} nicht gefunden (ID: {field_id})")
    db.commit()
    print("Fertig.")
finally:
    db.close()
