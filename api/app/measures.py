"""Behandlungen (Pflanzenschutz) eintragen, auflisten, löschen.

Einbau in main.py:
    from .measures import router as measures_router
    app.include_router(measures_router)

Anpassen: get_conn und current_user an die bestehende App binden (siehe unten).
Der Nachtjob liest die Einträge über TREATMENTS_SQL in jobs/pcf_jobs/store.py
(type = 'pflanzenschutz'); dort ist nichts zu ändern.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Kind = Literal["fungizid", "herbizid", "insektizid", "wachstumsregler"]
Unit = Literal["l/ha", "kg/ha", "g/ha"]
KIND_LABELS = {"fungizid": "Fungizid", "herbizid": "Herbizid", "insektizid": "Insektizid", "wachstumsregler": "Wachstumsregler"}


class MeasureIn(BaseModel):
    day: date
    kind: Kind
    product: Optional[str] = Field(default=None, max_length=120)
    amount: Optional[float] = Field(default=None, ge=0, le=10000)
    unit: Optional[Unit] = None

    @field_validator("day")
    @classmethod
    def _not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Datum liegt in der Zukunft")
        if v.year < date.today().year - 1:
            raise ValueError("Nur aktuelle und vorige Saison")
        return v

    @field_validator("product")
    @classmethod
    def _trim(cls, v):
        v = (v or "").strip()
        return v or None

    def model_post_init(self, _ctx) -> None:
        if (self.amount is None) != (self.unit is None):
            raise ValueError("Menge und Einheit nur gemeinsam angeben")


class MeasureOut(MeasureIn):
    id: str
    kindLabel: str

    # Rückgabewerte nicht erneut gegen "Zukunft" prüfen
    @field_validator("day")
    @classmethod
    def _not_future(cls, v: date) -> date:
        return v


# ---------------------------------------------------------------
# Datenbank (psycopg 3). Nur diese Funktionen greifen auf SQL zu.
# ---------------------------------------------------------------

def owns_field(conn, field_id: str, farm_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM fields WHERE id = %s AND farm_id = %s", (field_id, farm_id))
        return cur.fetchone() is not None


def list_measures(conn, field_id: str, season: int) -> list[MeasureOut]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id::text, day, kind, product, amount, unit FROM measures "
            "WHERE field_id = %s AND type = 'pflanzenschutz' AND day BETWEEN %s AND %s "
            "ORDER BY day DESC, created_at DESC",
            (field_id, date(season, 1, 1), date(season, 12, 31)),
        )
        rows = cur.fetchall()
    return [
        MeasureOut(id=r[0], day=r[1], kind=r[2] or "fungizid", product=r[3], amount=r[4], unit=r[5], kindLabel=KIND_LABELS.get(r[2] or "fungizid", "Behandlung"))
        for r in rows
    ]


def create_measure(conn, field_id: str, data: MeasureIn, user_id: Optional[str]) -> MeasureOut:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO measures (field_id, day, type, kind, product, amount, unit, created_by) "
            "VALUES (%s, %s, 'pflanzenschutz', %s, %s, %s, %s, %s) RETURNING id::text",
            (field_id, data.day, data.kind, data.product, data.amount, data.unit, user_id),
        )
        new_id = cur.fetchone()[0]
    conn.commit()
    return MeasureOut(id=new_id, kindLabel=KIND_LABELS[data.kind], **data.model_dump())


def delete_measure(conn, measure_id: str, farm_id: str) -> bool:
    """Löscht nur, wenn die Maßnahme zu einem Schlag des eigenen Betriebs gehört."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM measures m USING fields f WHERE m.id = %s AND m.field_id = f.id AND f.farm_id = %s",
            (measure_id, farm_id),
        )
        deleted = cur.rowcount
    conn.commit()
    return deleted == 1


# ---------------------------------------------------------------
# Router
# ---------------------------------------------------------------

try:
    import fastapi  # noqa: F401
except ImportError:  # nur in Tests ohne FastAPI
    fastapi = None

router = None
if fastapi is not None:
    from fastapi import APIRouter, Depends, HTTPException, Response, status

    from .db import get_conn            # ANPASSEN: bestehende DB Abhängigkeit (liefert psycopg Verbindung)
    from .auth import current_user      # ANPASSEN: liefert Objekt mit .id, .farm_id, .is_demo

    router = APIRouter(tags=["Behandlungen"])

    @router.get("/api/fields/{field_id}/measures", response_model=list[MeasureOut])
    def get_measures(field_id: str, season: int, conn=Depends(get_conn), user=Depends(current_user)):
        if not owns_field(conn, field_id, user.farm_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Schlag nicht gefunden")
        return list_measures(conn, field_id, season)

    @router.post("/api/fields/{field_id}/measures", response_model=MeasureOut, status_code=201)
    def post_measure(field_id: str, body: MeasureIn, conn=Depends(get_conn), user=Depends(current_user)):
        if getattr(user, "is_demo", False):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "In der Demo nicht möglich")
        if not owns_field(conn, field_id, user.farm_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Schlag nicht gefunden")
        return create_measure(conn, field_id, body, user.id)

    @router.delete("/api/measures/{measure_id}", status_code=204)
    def remove_measure(measure_id: str, conn=Depends(get_conn), user=Depends(current_user)):
        if getattr(user, "is_demo", False):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "In der Demo nicht möglich")
        if not delete_measure(conn, measure_id, user.farm_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Eintrag nicht gefunden")
        return Response(status_code=204)
