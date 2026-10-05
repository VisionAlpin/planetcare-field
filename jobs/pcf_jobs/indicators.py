"""Aus Rohdaten (NDVI Beobachtungen, Tageswetter, Behandlungen) die drei Teilwerte
zu einem Stichtag berechnen. Reine Funktionen, ohne Netz und Datenbank, voll testbar.

Alle Schwellen sind Vorschläge für Methodik v1.0 und werden im Förderprojekt
mit den Fachmentoren kalibriert.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

# Bewertungsfunktionen aus der API wiederverwenden (eine Quelle der Wahrheit)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
from app.scoring import protection_score, soil_cover_score, water_resilience_score  # noqa: E402

from .cdse import NdviObservation  # noqa: E402
from .era5 import DailyWeather  # noqa: E402

MIN_VALID_SHARE = 0.8        # mindestens 80 % wolkenfreie Pixel im Schlag
GREEN_NDVI = 0.3             # ab hier gilt der Boden als grün bedeckt
DRY_WINDOW_DAYS = 14         # Trockenphase: 14 Tage ...
DRY_MAX_PRECIP_MM = 10.0     # ... mit weniger als 10 mm Niederschlag
RISK_T_MIN, RISK_T_MAX = 10.0, 25.0   # Infektionsrisiko Blattkrankheiten Getreide (vereinfacht)
RISK_RH_MIN = 85.0
RISK_PRECIP_MIN = 1.0
SNAPSHOT_STEP_DAYS = 10
REFERENCE_WINDOW_DAYS = 30   # Vergleich Trockenphase mit normalen Phasen in diesem Abstand


@dataclass
class Snapshot:
    asof: date
    water: Optional[float]
    soil: Optional[float]
    protection: Optional[float]
    sources: dict = field(default_factory=dict)
    data_dates: dict = field(default_factory=dict)  # letzter verwendeter Messtag je Teilwert


def clean_ndvi(obs: Iterable[NdviObservation]) -> list[NdviObservation]:
    return [o for o in obs if o.valid_share >= MIN_VALID_SHARE and -0.2 <= o.mean <= 1.0]


def interpolate_daily(obs: list[NdviObservation], start: date, end: date) -> dict[date, float]:
    """Linear zwischen zwei Beobachtungen, nie über die erste oder letzte hinaus."""
    pts = sorted((o.day, o.mean) for o in obs if start <= o.day <= end)
    out: dict[date, float] = {}
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        span = (d1 - d0).days
        for i in range(span):
            out[d0 + timedelta(days=i)] = v0 + (v1 - v0) * i / span
    if pts:
        out[pts[-1][0]] = pts[-1][1]
    return out


def green_cover_days(daily_ndvi: dict[date, float]) -> tuple[int, int]:
    days = len(daily_ndvi)
    green = sum(1 for v in daily_ndvi.values() if v >= GREEN_NDVI)
    return green, days


def dry_days(weather: list[DailyWeather]) -> set[date]:
    """Tage, an denen die letzten 14 Tage zusammen unter 10 mm Niederschlag hatten."""
    by_day = {w.day: w.precip_mm for w in weather}
    out = set()
    for d in by_day:
        window = [by_day.get(d - timedelta(days=i)) for i in range(DRY_WINDOW_DAYS)]
        if all(v is not None for v in window) and sum(window) < DRY_MAX_PRECIP_MM:
            out.add(d)
    return out


def risk_days(weather: list[DailyWeather]) -> set[date]:
    """Vereinfachtes Infektionsmodell: mild (10 bis 25 °C) und nass (Regen ab 1 mm oder Feuchte ab 85 %)."""
    out = set()
    for w in weather:
        wet = w.precip_mm >= RISK_PRECIP_MIN or (w.rh_mean == w.rh_mean and w.rh_mean >= RISK_RH_MIN)
        if RISK_T_MIN <= w.t_mean_c <= RISK_T_MAX and wet:
            out.add(w.day)
    return out


def snapshot_dates(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=SNAPSHOT_STEP_DAYS)
    if out and out[-1] != end:
        out.append(end)
    return out


def compute_snapshot(
    asof: date,
    season_start: date,
    ndvi: list[NdviObservation],
    weather: list[DailyWeather],
    treatments: list[date],
) -> Snapshot:
    """Teilwerte mit allen Daten von Saisonbeginn bis einschließlich Stichtag."""
    ndvi_upto = [o for o in clean_ndvi(ndvi) if season_start <= o.day <= asof]
    weather_upto = [w for w in weather if season_start <= w.day <= asof]
    treat_upto = [t for t in treatments if season_start <= t <= asof]

    # Boden: Anteil der Tage mit grüner Bedeckung
    green, observed = green_cover_days(interpolate_daily(ndvi_upto, season_start, asof))
    soil = soil_cover_score(green, observed)

    # Wasser: NDVI in Trockenphasen gegenüber normalen Phasen
    dry = dry_days(weather_upto)
    water = None
    normal_obs = [o for o in ndvi_upto if o.day not in dry]
    if weather_upto and len(normal_obs) >= 3:
        dry_vals, ref_vals = [], []
        for o in (o for o in ndvi_upto if o.day in dry):
            refs = [n.mean for n in normal_obs if abs((n.day - o.day).days) <= REFERENCE_WINDOW_DAYS]
            if refs:
                dry_vals.append(o.mean)
                ref_vals.append(sum(refs) / len(refs))
        water = (
            water_resilience_score(dry_vals, ref_vals, min_reference=1)
            if dry_vals
            else water_resilience_score([], [n.mean for n in normal_obs])
        )

    # Pflanzenschutz: Behandlungen im Verhältnis zu Risikotagen
    protection = protection_score(treat_upto, risk_days(weather_upto)) if weather_upto else None

    last_ndvi = max((o.day for o in ndvi_upto), default=None)
    last_weather = max((w.day for w in weather_upto), default=None)
    return Snapshot(
        asof=asof,
        water=water,
        soil=soil,
        protection=protection,
        sources={"water": "sentinel2_era5", "soil": "sentinel2", "protection": "era5_treatments"},
        data_dates={
            "water": max(filter(None, [last_ndvi, last_weather]), default=None),
            "soil": last_ndvi,
            "protection": last_weather,
        },
    )
