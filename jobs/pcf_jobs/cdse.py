"""Sentinel 2 NDVI je Schlag über die Sentinel Hub Statistical API des
Copernicus Data Space Ecosystem (CDSE).

Warum Statistical API: Sie liefert pro Aufnahmetag direkt den mittleren NDVI
innerhalb des Schlagumrisses, inklusive Wolkenmaske. Es müssen keine Bilder
heruntergeladen werden. Das reicht für die Demo mit wenigen Schlägen.
Im Förderprojekt kommen die Werte aus den NOSTRADAMUS Data Cubes.

Zugang: kostenloses CDSE Konto, im Sentinel Hub Dashboard einen OAuth Client
anlegen, ID und Secret als CDSE_CLIENT_ID und CDSE_CLIENT_SECRET hinterlegen.
Doku: https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date

import requests

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
# Legacy Pfad, laut CDSE (März 2026) weiterhin gültig; neuer Pfad: /statistics/v1
STATS_URL = os.environ.get("CDSE_STATS_URL", "https://sh.dataspace.copernicus.eu/api/v1/statistics")

# NDVI mit Wolken- und Schattenmaske aus der Szenenklassifikation (SCL).
# Gültig sind nur Vegetation (4), unbewachsener Boden (5) und Wasser (6).
EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(s) {
  var valid = s.dataMask === 1 && (s.SCL === 4 || s.SCL === 5 || s.SCL === 6);
  var ndvi = (s.B08 + s.B04) === 0 ? 0 : (s.B08 - s.B04) / (s.B08 + s.B04);
  return { ndvi: [ndvi], dataMask: [valid ? 1 : 0] };
}
"""


@dataclass
class NdviObservation:
    day: date
    mean: float
    valid_share: float  # Anteil gültiger (wolkenfreier) Pixel im Schlag, 0 bis 1


class CdseClient:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None, session: requests.Session | None = None):
        self.client_id = client_id or os.environ.get("CDSE_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("CDSE_CLIENT_SECRET", "")
        self.session = session or requests.Session()
        self._token: str | None = None
        self._token_exp = 0.0

    def _get_token(self) -> str:
        # Token wiederverwenden, CDSE begrenzt Token Anfragen
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        r = self.session.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 600))
        return self._token

    def ndvi_series(self, geometry: dict, start: date, end: date) -> list[NdviObservation]:
        """Mittlerer NDVI je Aufnahmetag im Schlag (EPSG:4326 GeoJSON Polygon)."""
        body = {
            "input": {
                "bounds": {"geometry": geometry, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
                "data": [{"type": "sentinel-2-l2a", "dataFilter": {"maxCloudCoverage": 80}}],
            },
            "aggregation": {
                "timeRange": {"from": f"{start.isoformat()}T00:00:00Z", "to": f"{end.isoformat()}T23:59:59Z"},
                "aggregationInterval": {"of": "P1D"},
                "evalscript": EVALSCRIPT,
                "resx": 0.0001,  # ca. 10 m in Grad
                "resy": 0.0001,
            },
        }
        r = self.session.post(
            STATS_URL,
            json=body,
            headers={"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"},
            timeout=120,
        )
        r.raise_for_status()
        return parse_stats_response(r.json())


def parse_stats_response(payload: dict) -> list[NdviObservation]:
    """Wandelt die Antwort der Statistical API in Beobachtungen um. Tage ohne gültige Pixel fallen weg."""
    out: list[NdviObservation] = []
    for item in payload.get("data", []):
        if item.get("error"):
            continue
        try:
            stats = item["outputs"]["ndvi"]["bands"]["B0"]["stats"]
        except KeyError:
            continue
        sample = stats.get("sampleCount") or 0
        nodata = stats.get("noDataCount") or 0
        mean = stats.get("mean")
        if not sample or mean is None or mean != mean:  # NaN
            continue
        valid_share = (sample - nodata) / sample
        day = date.fromisoformat(item["interval"]["from"][:10])
        out.append(NdviObservation(day=day, mean=float(mean), valid_share=valid_share))
    return sorted(out, key=lambda o: o.day)
