"""Tests für die Bewertungslogik. Ausführen im Ordner api/:  python -m pytest -q"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scoring import (  # noqa: E402
    derive_hint,
    finalize_overview,
    protection_score,
    rating,
    regional_average,
    soil_cover_score,
    source_label,
    version_label,
)

# Antwort der Live API vom 5. Oktober 2026 (gekürzt)
LIVE = {
    "farm": {"id": "f1", "name": "Musterbetrieb Flachgau"},
    "field": {"id": "s1", "name": "Schlag Nord", "municipality": "Salzburg-Umgebung", "crop": "Winterweizen", "season": 2026,
              "geometry": {"type": "Polygon", "coordinates": [[[13.08, 47.92], [13.09, 47.92], [13.09, 47.91], [13.08, 47.91], [13.08, 47.92]]]}},
    "seasons": [2026, 2025],
    "fields": [{"id": "s1", "name": "Schlag Nord"}],
    "scores": {
        "water": {"available": True, "value": 78, "previousSeason": None, "regionalAverage": None, "source": "copernicus_gdo", "date": "2026-07-01"},
        "soil": {"available": True, "value": 57, "previousSeason": None, "regionalAverage": None, "source": "sentinel2", "date": "2026-07-01"},
        "protection": {"available": True, "value": 82, "previousSeason": None, "regionalAverage": None, "source": "Methodik v1.0", "date": "2026-10-05"},
    },
    "hint": None,
    "series": [
        {"label": "2025", "date": "2025-07-01", "water": 74, "soil": 52, "protection": 79, "total": 68},
        {"label": "2026", "date": "2026-07-01", "water": 78, "soil": 57, "protection": 82, "total": 72},
    ],
    "methodology": {"version": "1.0", "computedAt": "2026-10-04", "dataSources": ["Copernicus Sentinel-2", "EDO CDI"]},
}


def test_rating_grenzen():
    assert rating(70) == "gut"
    assert rating(69.4) == "mittel"
    assert rating(40) == "mittel"
    assert rating(39.4) == "kritisch"


def test_vorjahr_aus_reihe_und_reihe_nur_aktuelle_saison():
    out = finalize_overview(LIVE)
    assert out["scores"]["water"]["previousSeason"] == 74
    assert out["scores"]["soil"]["previousSeason"] == 52
    assert out["scores"]["protection"]["previousSeason"] == 79
    assert [r["date"] for r in out["series"]] == ["2026-07-01"]
    assert "label" not in out["series"][0] and "total" not in out["series"][0]


def test_region_null_statt_null_wert():
    out = finalize_overview(LIVE)
    assert out["scores"]["water"]["regionalAverage"] is None
    assert out["total"]["regionalAverage"] is None
    assert out["total"]["previousSeason"] == (74 + 52 + 79) / 3


def test_region_erst_ab_drei_schlaegen():
    assert regional_average([70, 72]) is None
    assert regional_average([70, 72, 68]) == 70
    out = finalize_overview(LIVE, regional_values={"water": [70, 72, 68], "soil": [60, 62, 64], "protection": [80, 80, 80]})
    assert out["scores"]["soil"]["regionalAverage"] == 62


def test_quellen_und_version():
    out = finalize_overview(LIVE)
    assert out["scores"]["water"]["source"] == "Copernicus EDO (CDI)"
    assert out["scores"]["soil"]["source"] == "Sentinel 2"
    assert out["methodology"]["version"] == "v1.0"
    assert source_label("unbekannt") == "unbekannt"
    assert version_label("v1.0") == "v1.0"


def test_gesamt_und_hinweis():
    out = finalize_overview(LIVE)
    assert out["total"]["value"] == round((78 + 57 + 82) / 3, 1)
    assert out["total"]["rating"] == "gut"
    assert out["hint"]["text"].startswith("Boden ist mit 57")


def test_hinweis_mit_region():
    scores = {"water": {"available": True, "value": 60, "regionalAverage": 70},
              "soil": {"available": True, "value": 45, "regionalAverage": 48}}
    assert derive_hint(scores)["text"].startswith("Wasser liegt mit 60 um 10 Punkte")


def test_gesamt_erst_ab_zwei_teilwerten():
    raw = dict(LIVE, scores={"water": LIVE["scores"]["water"], "soil": {"available": False}, "protection": {"available": False}})
    assert finalize_overview(raw)["total"] == {"available": False}


def test_bodenbedeckung():
    assert soil_cover_score(146, 292) == 50
    assert soil_cover_score(10, 20) is None


def test_pflanzenschutz():
    risk = {date(2026, 5, 10), date(2026, 6, 2)}
    assert protection_score([], risk) == 100
    assert protection_score([date(2026, 5, 11), date(2026, 7, 20)], risk) == 50
    assert protection_score([date(2026, 6, 1)], risk) == 100
