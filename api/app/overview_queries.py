"""Liest die Ergebnisse des Nachtjobs (score_snapshots) für GET /api/fields/{id}/overview.

Einbau im bestehenden Endpunkt (conn = psycopg Verbindung):

    from .overview_queries import scores_and_series, previous_scores, regional_values, last_job_run
    from .scoring import finalize_overview

    raw = load_overview_from_db(field_id, season, user)       # farm, field, fields, seasons, methodology
    raw["scores"], raw["series"] = scores_and_series(conn, field_id, season)
    return finalize_overview(raw, previous_scores(conn, field_id, season - 1), regional_values(conn, field_id, season))
"""

from __future__ import annotations

import json

EXPLANATIONS = {
    "water": "Wie gut der Bestand seine Vitalität in Trockenphasen hält: Vegetationsindex (Sentinel 2) in Phasen mit weniger als 10 mm Regen in 14 Tagen (ERA5) im Vergleich zu normalen Phasen. 100 = kein Einbruch.",
    "soil": "Anteil der Tage seit Saisonbeginn, an denen der Boden grün bedeckt war (Vegetationsindex ab 0,3, Sentinel 2). Bedeckter Boden schützt vor Erosion und baut Humus auf. 100 = durchgehend bedeckt.",
    "protection": "Anteil der Pflanzenschutz Behandlungen, die gezielt bei erhöhtem Krankheitsrisiko erfolgten (mildes, feuchtes Wetter laut ERA5, plus/minus 3 Tage). Keine Behandlung = 100. Höher ist besser.",
}
KEYS = ("water", "soil", "protection")


def _load(v):
    return v if isinstance(v, dict) else json.loads(v or "{}")


def scores_and_series(conn, field_id: str, season: int) -> tuple[dict, list]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT asof, water, soil, protection, sources, data_dates FROM score_snapshots "
            "WHERE field_id = %s AND season = %s ORDER BY asof",
            (field_id, season),
        )
        rows = cur.fetchall()
    series = [{"date": r[0].isoformat(), "water": r[1], "soil": r[2], "protection": r[3]} for r in rows]
    scores = {k: {"available": False, "explanation": EXPLANATIONS[k]} for k in KEYS}
    if rows:
        last = rows[-1]
        sources, dates = _load(last[4]), _load(last[5])
        for i, k in enumerate(KEYS, start=1):
            if last[i] is not None:
                scores[k] = {
                    "available": True,
                    "value": float(last[i]),
                    "source": sources.get(k),
                    "date": dates.get(k) or last[0].isoformat(),  # Datum der letzten MESSUNG, nicht der Berechnung
                    "explanation": EXPLANATIONS[k],
                }
    return scores, series


def previous_scores(conn, field_id: str, season: int) -> dict:
    """Letzter Stichtag der Vorsaison. Leeres Dict, wenn die Vorsaison nicht berechnet ist."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT water, soil, protection FROM score_snapshots WHERE field_id = %s AND season = %s "
            "ORDER BY asof DESC LIMIT 1",
            (field_id, season),
        )
        r = cur.fetchone()
    return {k: v for k, v in zip(KEYS, r or ()) if v is not None}


def regional_values(conn, field_id: str, season: int) -> dict:
    """Aktuelle Werte der anderen Schläge mit gleicher Kultur und Region (ohne den eigenen).

    finalize_overview() bildet daraus den Durchschnitt erst ab 3 Schlägen.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH me AS (SELECT crop, region_code FROM fields WHERE id = %s),
            latest AS (
              SELECT DISTINCT ON (s.field_id) s.field_id, s.water, s.soil, s.protection
              FROM score_snapshots s JOIN fields f ON f.id = s.field_id, me
              WHERE s.season = %s AND f.id <> %s AND f.crop = me.crop AND f.region_code = me.region_code
              ORDER BY s.field_id, s.asof DESC
            )
            SELECT water, soil, protection FROM latest
            """,
            (field_id, season, field_id),
        )
        rows = cur.fetchall()
    return {k: [r[i] for r in rows if r[i] is not None] for i, k in enumerate(KEYS)}


def last_job_run(conn, stale_hours: int = 6) -> dict | None:
    """Für /health: wann lief der Nachtjob zuletzt und wie. Hängende Läufe erscheinen als 'stale'."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT started_at, finished_at, status, fields_ok, fields_failed, "
            "(status = 'running' AND started_at < now() - make_interval(hours => %s)) AS stale "
            "FROM job_runs ORDER BY id DESC LIMIT 1",
            (stale_hours,),
        )
        r = cur.fetchone()
    if not r:
        return None
    return {
        "startedAt": r[0].isoformat() if r[0] else None,
        "finishedAt": r[1].isoformat() if r[1] else None,
        "status": "stale" if r[5] else r[2],
        "fieldsOk": r[3],
        "fieldsFailed": r[4],
    }
