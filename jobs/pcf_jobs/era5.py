"""Tageswetter je Schlag aus ERA5-Land (Copernicus Climate Data Store).

Datensatz: reanalysis-era5-land-timeseries (Punktzeitreihe, schnell abrufbar).
Hinweis: Der CDS kennzeichnet den Datensatz als experimentell und nicht für
den Betrieb empfohlen. Für den Prototyp (Phase 0) passt er; im Förderprojekt
kommen Wetterdaten aus dem NOSTRADAMUS IoT Observatory und den Data Cubes.

Zugang: kostenloses CDS Konto, Lizenz des Datensatzes im CDS einmal akzeptieren,
API Schlüssel als CDS_API_KEY hinterlegen. Paket: pip install cdsapi
Die genauen Parameter bitte einmal gegen die Datensatzseite prüfen:
https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-timeseries
"""

from __future__ import annotations

import csv
import io
import math
import os
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

DATASET = "reanalysis-era5-land-timeseries"
VARIABLES = ["2m_temperature", "2m_dewpoint_temperature", "total_precipitation"]


@dataclass
class DailyWeather:
    day: date
    t_mean_c: float
    rh_mean: float  # relative Feuchte in Prozent
    precip_mm: float


def fetch_daily_weather(lat: float, lon: float, start: date, end: date) -> list[DailyWeather]:
    import cdsapi  # erst hier importieren, damit Tests ohne Paket laufen

    client = cdsapi.Client(url=os.environ.get("CDS_API_URL", "https://cds.climate.copernicus.eu/api"), key=os.environ["CDS_API_KEY"])
    request = {
        "variable": VARIABLES,
        "location": {"longitude": round(lon, 3), "latitude": round(lat, 3)},
        "date": [f"{start.isoformat()}/{end.isoformat()}"],
        "data_format": "csv",
    }
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "era5")
        client.retrieve(DATASET, request).download(target)
        return parse_download(target)


def parse_download(path: str) -> list[DailyWeather]:
    """Der CDS liefert je nach Anfrage eine CSV oder eine ZIP mit einer CSV je Variable."""
    texts: list[str] = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            texts = [z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".csv")]
    else:
        with open(path, encoding="utf-8") as f:
            texts = [f.read()]
    rows: list[dict] = []
    for t in texts:
        rows.extend(csv.DictReader(io.StringIO(t)))
    return hourly_rows_to_daily(rows)


def _rh(t_c: float, td_c: float) -> float:
    """Relative Feuchte aus Temperatur und Taupunkt (Magnus Formel)."""
    a, b = 17.625, 243.04
    return max(0.0, min(100.0, 100.0 * math.exp(a * td_c / (b + td_c)) / math.exp(a * t_c / (b + t_c))))


def hourly_rows_to_daily(rows: list[dict]) -> list[DailyWeather]:
    """Stündliche Werte (Kelvin, Meter Niederschlag) zu Tageswerten zusammenfassen.

    Erwartete Spalten: valid_time und je Variable t2m, d2m, tp (Kurzname) oder der lange Name.
    Zeilen verschiedener Variablen mit gleicher Zeit werden zusammengeführt.
    """
    by_time: dict[str, dict] = defaultdict(dict)
    for r in rows:
        ts = r.get("valid_time") or r.get("time") or r.get("date")
        if not ts:
            continue
        for key, short in (("t2m", "t2m"), ("2m_temperature", "t2m"), ("d2m", "d2m"), ("2m_dewpoint_temperature", "d2m"), ("tp", "tp"), ("total_precipitation", "tp")):
            if r.get(key) not in (None, ""):
                by_time[ts][short] = float(r[key])
    days: dict[date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for ts, v in by_time.items():
        d = datetime.fromisoformat(ts.replace("Z", "").replace(" ", "T")).date()
        if "t2m" in v:
            days[d]["t"].append(v["t2m"] - 273.15)
        if "t2m" in v and "d2m" in v:
            days[d]["rh"].append(_rh(v["t2m"] - 273.15, v["d2m"] - 273.15))
        if "tp" in v:
            days[d]["p"].append(max(0.0, v["tp"]) * 1000.0)  # m -> mm, stündlich (de-akkumuliert)
    out = []
    for d in sorted(days):
        x = days[d]
        if not x["t"]:
            continue
        out.append(
            DailyWeather(
                day=d,
                t_mean_c=sum(x["t"]) / len(x["t"]),
                rh_mean=sum(x["rh"]) / len(x["rh"]) if x["rh"] else float("nan"),
                precip_mm=sum(x["p"]),
            )
        )
    return out
