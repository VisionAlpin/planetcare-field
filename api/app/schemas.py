"""PlanetCare Field: Antwortmodelle und Sicherheitsschema (Pydantic v2 / FastAPI)

Zweck: Die OpenAPI Beschreibung (/openapi.json, docs/openapi.yaml) zeigt damit
die vollständige Datenstruktur und die Absicherung der Endpunkte. Das ist im
NOSTRADAMUS Aufruf Pflicht (dokumentierte REST Schnittstellen, OpenAPI v3).

Einbau im Router:

    from fastapi import Depends
    from .schemas import Overview, FieldProfile, DemandEventBatch, require_service_key
    from .scoring import finalize_overview

    @router.get("/api/fields/{field_id}/overview", response_model=Overview)
    def get_overview(field_id: str, season: int, user=Depends(current_user_or_demo)):
        raw = load_overview_from_db(field_id, season, user)       # bestehende Funktion
        prev = load_previous_season_scores(field_id, season - 1)  # {"water": 74, ...} oder {}
        regional = load_regional_values(field_id, season)         # {"water": [..], ...} oder {}
        return finalize_overview(raw, prev, regional)

    @router.get("/api/products/{gtin}/field-profile", response_model=FieldProfile,
                dependencies=[Depends(require_service_key)])
    ...

    @router.post("/api/demand-events", status_code=202, dependencies=[Depends(require_service_key)])
    def post_events(batch: DemandEventBatch): ...
"""

from __future__ import annotations

import os
import secrets
from typing import Literal, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------
# Sicherheit: Server zu Server Schlüssel für die Verbraucher App
# --------------------------------------------------------------------------

service_bearer = HTTPBearer(
    scheme_name="ServiceApiKey",
    description="Schlüssel für den Server der Verbraucher App (Umgebungsvariable SERVICE_API_KEY). Nie im Browser verwenden.",
    auto_error=False,
)


def require_service_key(creds: Optional[HTTPAuthorizationCredentials] = Depends(service_bearer)) -> None:
    expected = os.environ.get("SERVICE_API_KEY", "")
    if not expected or creds is None or not secrets.compare_digest(creds.credentials, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiger oder fehlender Schlüssel")


# --------------------------------------------------------------------------
# Übersicht
# --------------------------------------------------------------------------

Rating = Literal["gut", "mittel", "kritisch"]


class Geometry(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]] = Field(description="GeoJSON Polygon, WGS84, [lon, lat]")


class Farm(BaseModel):
    id: str
    name: str


class FieldInfo(BaseModel):
    id: str
    name: str
    municipality: str
    crop: str
    season: int
    geometry: Geometry
    areaHa: Optional[float] = Field(default=None, description="Fläche in ha, aus PostGIS ST_Area(geom::geography)/10000")
    regionCode: Optional[str] = Field(default=None, description="ISO 3166-2, z. B. AT-5")


class FieldRef(BaseModel):
    id: str
    name: str


class Score(BaseModel):
    available: bool
    value: Optional[float] = Field(default=None, ge=0, le=100, description="0 bis 100, höher = besser")
    rating: Optional[Rating] = None
    previousSeason: Optional[float] = Field(default=None, description="Wert der Vorsaison, null wenn unbekannt")
    regionalAverage: Optional[float] = Field(default=None, description="Durchschnitt vergleichbarer Schläge, null unter 3 Schlägen")
    source: Optional[str] = Field(default=None, description="Anzeigename der Quelle, z. B. 'Sentinel 2'")
    date: Optional[str] = Field(default=None, description="Datum des letzten Messwerts, ISO 8601")
    explanation: Optional[str] = None


class Total(BaseModel):
    available: bool
    value: Optional[float] = None
    rating: Optional[Rating] = None
    previousSeason: Optional[float] = None
    regionalAverage: Optional[float] = None


class Scores(BaseModel):
    water: Score
    soil: Score
    protection: Score


class Hint(BaseModel):
    text: str
    link: Optional[str] = None


class SeriesPoint(BaseModel):
    date: str
    water: Optional[float] = None
    soil: Optional[float] = None
    protection: Optional[float] = None


class Methodology(BaseModel):
    version: str = Field(description="z. B. 'v1.0'")
    computedAt: Optional[str] = None
    dataSources: list[str]


class Overview(BaseModel):
    farm: Farm
    field: FieldInfo
    seasons: list[int]
    fields: list[FieldRef]
    scores: Scores
    total: Total
    hint: Optional[Hint] = None
    series: list[SeriesPoint] = Field(description="Nur Messungen der aktuellen Saison, aufsteigend nach Datum")
    methodology: Methodology


# --------------------------------------------------------------------------
# Schnittstellen zur Verbraucher App
# --------------------------------------------------------------------------

class FieldProfile(BaseModel):
    gtin: str
    verified: bool
    profileScore: Optional[float] = None
    scores: dict[str, Optional[float]]
    region: Optional[str] = None
    harvestYear: Optional[int] = None
    methodology: str


EventType = Literal["scan", "compare", "compare_choice", "filter_verified", "survey_wtp"]


class DemandEvent(BaseModel):
    type: EventType
    gtin: Optional[str] = None
    comparedWith: list[str] = []
    category: str
    region: str = Field(description="Bundesland Code nach ISO 3166-2, z. B. 'AT-5'")
    week: str = Field(description="Kalenderwoche nach ISO 8601, z. B. '2026-W41'")
    panel: bool = False
    value: Optional[float] = Field(default=None, description="Nur bei survey_wtp: Aufpreis in Prozent")

    @field_validator("week")
    @classmethod
    def _week(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"\d{4}-W\d{2}", v):
            raise ValueError("week muss das Format JJJJ-Www haben")
        return v


class DemandEventBatch(BaseModel):
    events: list[DemandEvent] = Field(max_length=1000)
