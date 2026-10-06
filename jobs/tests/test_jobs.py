"""Tests für den Nachtjob, ohne Netz und ohne Datenbank.  Ausführen im Ordner jobs/:  python -m pytest -q"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcf_jobs.cdse import NdviObservation, parse_stats_response  # noqa: E402
from pcf_jobs.era5 import DailyWeather, hourly_rows_to_daily  # noqa: E402
from pcf_jobs.indicators import (  # noqa: E402
    clean_ndvi, compute_snapshot, dry_days, interpolate_daily, risk_days, snapshot_dates,
)
from pcf_jobs.run_nightly import process_field, season_window  # noqa: E402
from pcf_jobs.set_field_geometry import check_bounds, extract_polygon  # noqa: E402
from pcf_jobs.store import FieldRow  # noqa: E402

D = date


def test_parse_statistical_api():
    payload = {"data": [
        {"interval": {"from": "2026-05-03T00:00:00Z", "to": "2026-05-04T00:00:00Z"},
         "outputs": {"ndvi": {"bands": {"B0": {"stats": {"mean": 0.71, "sampleCount": 1000, "noDataCount": 50}}}}}},
        {"interval": {"from": "2026-05-08T00:00:00Z", "to": "2026-05-09T00:00:00Z"},
         "outputs": {"ndvi": {"bands": {"B0": {"stats": {"mean": "NaN", "sampleCount": 1000, "noDataCount": 1000}}}}}},
        {"interval": {"from": "2026-05-01T00:00:00Z", "to": "2026-05-02T00:00:00Z"}, "error": {"type": "EXECUTION_ERROR"}},
    ]}
    payload["data"][1]["outputs"]["ndvi"]["bands"]["B0"]["stats"]["mean"] = float("nan")
    obs = parse_stats_response(payload)
    assert len(obs) == 1 and obs[0].day == D(2026, 5, 3) and abs(obs[0].valid_share - 0.95) < 1e-9


def test_era5_stuendlich_zu_taeglich():
    rows = []
    for h in range(24):
        ts = f"2026-06-01 {h:02d}:00:00"
        rows.append({"valid_time": ts, "t2m": "290.15", "d2m": "288.15", "tp": "0.0001"})
    days = hourly_rows_to_daily(rows)
    assert len(days) == 1
    w = days[0]
    assert abs(w.t_mean_c - 17.0) < 1e-6 and abs(w.precip_mm - 2.4) < 1e-6 and 85 < w.rh_mean < 90


def test_wolken_filter_und_interpolation():
    obs = [NdviObservation(D(2026, 4, 1), 0.2, 0.9), NdviObservation(D(2026, 4, 11), 0.6, 0.95), NdviObservation(D(2026, 4, 6), 0.9, 0.3)]
    clean = clean_ndvi(obs)
    assert len(clean) == 2
    daily = interpolate_daily(clean, D(2026, 3, 1), D(2026, 4, 30))
    assert len(daily) == 11 and abs(daily[D(2026, 4, 6)] - 0.4) < 1e-9


def _weather(start, days, precip=5.0, t=15.0, rh=70.0):
    return [DailyWeather(start + timedelta(days=i), t, rh, precip) for i in range(days)]


def test_trockenphase_und_risikotage():
    w = _weather(D(2026, 6, 1), 20, precip=0.2)
    assert D(2026, 6, 14) in dry_days(w) and D(2026, 6, 13) not in dry_days(w)
    assert risk_days([DailyWeather(D(2026, 6, 1), 15, 90, 0), DailyWeather(D(2026, 6, 2), 30, 95, 5)]) == {D(2026, 6, 1)}


def test_stichtage():
    d = snapshot_dates(D(2026, 4, 1), D(2026, 4, 25))
    assert d == [D(2026, 4, 1), D(2026, 4, 11), D(2026, 4, 21), D(2026, 4, 25)]


def _season_data():
    start = D(2026, 3, 1)
    ndvi = [NdviObservation(start + timedelta(days=i), 0.15 + min(i, 80) * 0.008, 0.95) for i in range(0, 200, 5)]
    weather = _weather(start, 200, precip=3.0)
    # Trockenphase im Juli mit leichtem NDVI Einbruch
    for w in weather:
        if D(2026, 7, 1) <= w.day <= D(2026, 7, 31):
            w.precip_mm = 0.0
    for o in ndvi:
        if D(2026, 7, 14) <= o.day <= D(2026, 7, 31):
            o.mean -= 0.1
    return start, ndvi, weather


def test_snapshot_alle_drei_teilwerte():
    start, ndvi, weather = _season_data()
    snap = compute_snapshot(D(2026, 8, 15), start, ndvi, weather, [D(2026, 5, 20)])
    assert 0 <= snap.water < 100 and 0 < snap.soil < 100 and snap.protection == 100
    assert snap.sources["soil"] == "sentinel2" and snap.data_dates["soil"] <= D(2026, 8, 15)


class FakeCdse:
    def __init__(self, ndvi): self.ndvi = ndvi
    def ndvi_series(self, geometry, start, end): return [o for o in self.ndvi if start <= o.day <= end]


class FakeStore:
    def __init__(self): self.snaps, self.ind, self.commits = [], [], 0
    def treatments(self, *a): return []
    def save_indicators(self, fid, rows): self.ind.extend(rows)
    def save_snapshot(self, fid, season, snap, meth): self.snaps.append(snap)
    def commit(self): self.commits += 1


def test_process_field_ende_zu_ende():
    start, ndvi, weather = _season_data()
    field = FieldRow("f1", "Schlag Nord", {"type": "Polygon", "coordinates": []}, None, 47.9, 13.0, 12.4)
    store = FakeStore()
    n = process_field(field, 2026, D(2026, 9, 1), store, FakeCdse(ndvi), lambda *a: weather)
    assert n == len(store.snaps) == 17 and store.commits == 1
    assert store.snaps[-1].asof == D(2026, 9, 1)


def test_unplausible_flaeche_bricht_ab():
    field = FieldRow("f1", "Rechteck", {}, None, 47.9, 13.0, 82.9 * 2)
    try:
        process_field(field, 2026, D(2026, 9, 1), FakeStore(), FakeCdse([]), lambda *a: [])
        assert False
    except ValueError as e:
        assert "unplausibel" in str(e)


def test_saisonfenster():
    assert season_window(2025, D(2026, 10, 5)) == (D(2025, 3, 1), D(2025, 4, 1), D(2025, 10, 31))


def test_geojson_pruefung():
    poly = {"type": "Polygon", "coordinates": [[[13.0, 47.9], [13.01, 47.9], [13.01, 47.91], [13.0, 47.9]]]}
    assert extract_polygon({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": poly}]}) == poly
    check_bounds(poly)
    try:
        check_bounds({"type": "Polygon", "coordinates": [[[47.9, 13.0]]]})
        assert False
    except SystemExit:
        pass


def test_lauf_wird_immer_abgeschlossen(monkeypatch=None):
    """Auch wenn alles scheitert (z. B. Zugangsdaten fehlen), endet der Lauf nicht auf 'running'."""
    import pcf_jobs.run_nightly as rn
    import pcf_jobs.store as st

    calls = {}

    class S:
        def __init__(self): pass
        def close_stale_runs(self): calls["stale"] = True; return 1
        def start_run(self): return 7
        def fields(self): raise RuntimeError("DB weg")
        def rollback(self): pass
        def finish_run(self, run_id, status, ok, failed, msg): calls["finish"] = (run_id, status, msg)

    orig = st.PostgresStore
    st.PostgresStore = S
    try:
        code = rn.main(["--season", "2026"])
    finally:
        st.PostgresStore = orig
    assert code == 1 and calls["stale"] and calls["finish"][0] == 7 and calls["finish"][1] == "failed" and "DB weg" in calls["finish"][2]
