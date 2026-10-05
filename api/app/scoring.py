"""PlanetCare Field: Bewertungslogik (Methodik v1.0)

Reine Funktionen ohne Datenbankzugriff. Sie werden im Endpunkt
GET /api/fields/{id}/overview aufgerufen, NACHDEM die Rohwerte aus der
Datenbank geladen wurden. Siehe finalize_overview() unten.

Alle Formeln sind ein Startvorschlag und werden im Förderprojekt mit den
Fachmentoren kalibriert. Grundregel: Fehlt ein Wert, wird nichts geschätzt,
sondern None geliefert.
"""

from __future__ import annotations

from datetime import date
from statistics import mean
from typing import Iterable, Optional

METHODOLOGY_VERSION = "v1.0"
MIN_SCORES_FOR_TOTAL = 2
SCORE_KEYS = ("water", "soil", "protection")
SCORE_LABELS = {"water": "Wasser", "soil": "Boden", "protection": "Pflanzenschutz"}

# Technische Quellenschlüssel -> Anzeigenamen im Dashboard
SOURCE_LABELS = {
    "copernicus_edo": "Copernicus EDO (CDI)",
    "copernicus_gdo": "Copernicus EDO (CDI)",  # Europa: EDO verwenden, nicht GDO
    "edo_cdi": "Copernicus EDO (CDI)",
    "sentinel2": "Sentinel 2",
    "sentinel-2": "Sentinel 2",
    "era5": "ERA5",
    "soilgrids": "SoilGrids",
    "treatments": "Einträge",
    "era5_treatments": "ERA5 + Einträge",
    "sentinel2_soilgrids": "Sentinel 2 + SoilGrids",
}


# --------------------------------------------------------------------------
# Allgemeine Hilfen
# --------------------------------------------------------------------------

def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v  # v == v filtert NaN


def mean_or_none(values: Iterable) -> Optional[float]:
    """Mittelwert nur, wenn ALLE Werte vorhanden sind. Sonst None (nie 0!)."""
    vals = list(values)
    if not vals or not all(is_num(v) for v in vals):
        return None
    return float(mean(vals))


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def source_label(src: Optional[str]) -> Optional[str]:
    if not src:
        return src
    return SOURCE_LABELS.get(str(src).lower(), src)


def version_label(v: Optional[str]) -> str:
    v = (v or METHODOLOGY_VERSION).strip()
    return v if v.lower().startswith("v") else f"v{v}"


def rating(value: float) -> str:
    """gut ab 70, mittel 40 bis 69, kritisch unter 40 (auf ganze Zahl gerundet)."""
    v = round(value)
    if v >= 70:
        return "gut"
    if v >= 40:
        return "mittel"
    return "kritisch"


# --------------------------------------------------------------------------
# Teilwerte (Vorschlag Methodik v1.0)
# --------------------------------------------------------------------------

def soil_cover_score(days_green_cover: int, days_observed: int) -> Optional[float]:
    """Boden: Anteil der beobachteten Tage mit grüner Bodenbedeckung (NDVI > 0,3).

    Bedeckter Boden schützt vor Erosion und baut Humus auf. 100 = ganzjährig bedeckt.
    Nicht verwenden: räumliche Variabilität des NDVI (misst keine Bodengesundheit).
    """
    if not days_observed or days_observed < 30:
        return None
    return clamp(100.0 * days_green_cover / days_observed)


def protection_score(treatment_dates: list[date], risk_dates: set[date], window_days: int = 3) -> Optional[float]:
    """Pflanzenschutz: Anteil der Behandlungen, die gezielt bei erhöhtem Krankheitsrisiko erfolgten.

    Eine Behandlung gilt als gezielt, wenn innerhalb von +/- window_days ein Risikotag
    (aus ERA5 Wetter) liegt. 100 = gut (keine oder nur gezielte Behandlungen).
    Keine Behandlungen in der Saison = 100.
    """
    if risk_dates is None:
        return None
    if not treatment_dates:
        return 100.0
    targeted = sum(
        1 for t in treatment_dates
        if any(abs((t - r).days) <= window_days for r in risk_dates)
    )
    return clamp(100.0 * targeted / len(treatment_dates))


def total_score(scores: dict) -> Optional[float]:
    """Gesamt = Mittelwert der verfügbaren Teilwerte, erst ab MIN_SCORES_FOR_TOTAL."""
    vals = [s["value"] for s in scores.values() if s and s.get("available") and is_num(s.get("value"))]
    if len(vals) < MIN_SCORES_FOR_TOTAL:
        return None
    return float(mean(vals))


def regional_average(values: Iterable) -> Optional[float]:
    """Regionaler Durchschnitt aus den Werten vergleichbarer Schläge (gleiche Kultur, gleicher Bezirk).

    Erst ab 3 Schlägen, sonst None (sonst wäre ein einzelner Nachbar identifizierbar).
    """
    vals = [v for v in values if is_num(v)]
    if len(vals) < 3:
        return None
    return float(mean(vals))


def derive_hint(scores: dict) -> Optional[dict]:
    """Ein Hinweis: größter Abstand unter dem Regionsschnitt, sonst schwächster Teilwert unter 70."""
    avail = [
        (k, s) for k, s in scores.items()
        if s and s.get("available") and is_num(s.get("value"))
    ]
    gaps = [(k, s) for k, s in avail if is_num(s.get("regionalAverage")) and s["value"] < s["regionalAverage"]]
    if gaps:
        k, s = min(gaps, key=lambda ks: ks[1]["value"] - ks[1]["regionalAverage"])
        diff = round(s["regionalAverage"] - s["value"])
        return {
            "text": f"{SCORE_LABELS[k]} liegt mit {round(s['value'])} um {diff} Punkte unter dem regionalen Durchschnitt.",
            "link": "#felder",
        }
    weak = [(k, s) for k, s in avail if s["value"] < 70]
    if weak:
        k, s = min(weak, key=lambda ks: ks[1]["value"])
        return {
            "text": f"{SCORE_LABELS[k]} ist mit {round(s['value'])} der schwächste Teilwert. Hier liegt das größte Verbesserungspotenzial.",
            "link": "#felder",
        }
    return None


# --------------------------------------------------------------------------
# Antwort bereinigen
# --------------------------------------------------------------------------

def finalize_overview(
    raw: dict,
    previous_scores: Optional[dict] = None,
    regional_values: Optional[dict] = None,
) -> dict:
    """Bereinigt die Antwort von /overview vor der Auslieferung.

    raw              Antwort wie bisher (farm, field, scores, series, methodology ...)
    previous_scores  Teilwerte der Vorsaison, z. B. {"water": 74, "soil": 52, "protection": 79}
    regional_values  Werte vergleichbarer Schläge je Teilwert, z. B. {"water": [70, 72, 68], ...}

    Ergebnis:
    - previousSeason und regionalAverage befüllt oder ausdrücklich None
    - Quellen als Anzeigenamen
    - Reihe nur mit Messungen der aktuellen Saison, sortiert
    - Vorjahreswerte, die noch in der Reihe stehen, wandern nach previousSeason
    - Hinweis erzeugt, falls keiner vorhanden
    - Methodikversion einheitlich "v1.0"
    """
    out = dict(raw)
    season = str(out["field"]["season"])
    prev_season = str(int(season) - 1)
    previous_scores = dict(previous_scores or {})
    regional_values = regional_values or {}

    # Vorjahreswerte aus der Reihe übernehmen, falls sie dort (fälschlich) stehen
    series = [r for r in (out.get("series") or []) if r and r.get("date")]
    prev_rows = sorted((r for r in series if str(r["date"])[:4] == prev_season), key=lambda r: r["date"])
    if prev_rows:
        last_prev = prev_rows[-1]
        for k in SCORE_KEYS:
            if not is_num(previous_scores.get(k)) and is_num(last_prev.get(k)):
                previous_scores[k] = last_prev[k]

    out["series"] = sorted(
        (
            {key: r[key] for key in ("date", *SCORE_KEYS) if key in r}
            for r in series
            if str(r["date"])[:4] == season
        ),
        key=lambda r: r["date"],
    )

    scores = {}
    for k in SCORE_KEYS:
        s = dict((out.get("scores") or {}).get(k) or {"available": False})
        if s.get("available") and is_num(s.get("value")):
            s["value"] = round(float(s["value"]), 1)
            prev = previous_scores.get(k)
            s["previousSeason"] = float(prev) if is_num(prev) else None
            if k in regional_values:
                s["regionalAverage"] = regional_average(regional_values[k])
            else:
                s["regionalAverage"] = float(s["regionalAverage"]) if is_num(s.get("regionalAverage")) else None
            s["rating"] = rating(s["value"])
            s["source"] = source_label(s.get("source"))
        else:
            s = {"available": False, "explanation": s.get("explanation")}
        scores[k] = s
    out["scores"] = scores

    total = total_score(scores)
    out["total"] = (
        {
            "available": True,
            "value": round(total, 1),
            "rating": rating(total),
            "previousSeason": mean_or_none(scores[k]["previousSeason"] for k in SCORE_KEYS if scores[k]["available"]),
            "regionalAverage": mean_or_none(scores[k]["regionalAverage"] for k in SCORE_KEYS if scores[k]["available"]),
        }
        if total is not None
        else {"available": False}
    )

    if not (out.get("hint") or {}).get("text"):
        out["hint"] = derive_hint(scores)

    meth = dict(out.get("methodology") or {})
    meth["version"] = version_label(meth.get("version"))
    out["methodology"] = meth
    return out
