"""Tests v0.5: Behandlungen und Brücke zur Verbraucher App.  Im Ordner api/:  python -m pytest -q"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bridge import (  # noqa: E402
    MIN_EVENTS, DemandEventBatch, DemandEventIn, build_signal, field_profile, iso_weeks_back,
    preference_rate, weighted_profile, wtp_median,
)
from app.measures import MeasureIn, create_measure, delete_measure, list_measures  # noqa: E402


class Cur:
    def __init__(self, conn): self.conn = conn; self.rowcount = conn.rowcount
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def execute(self, sql, params=()): self.conn.log.append((sql, params))
    def executemany(self, sql, rows): self.conn.log.append((sql, list(rows)))
    def fetchall(self): return self.conn.rows
    def fetchone(self): return self.conn.rows[0] if self.conn.rows else None


class Conn:
    def __init__(self, rows=None, rowcount=1): self.rows, self.rowcount, self.log, self.commits = rows or [], rowcount, [], 0
    def cursor(self): return Cur(self)
    def commit(self): self.commits += 1


# ---------- Behandlungen ----------

def test_measure_validierung():
    MeasureIn(day=date.today(), kind="fungizid")
    MeasureIn(day=date.today(), kind="herbizid", product="  Mittel X ", amount=1.5, unit="l/ha")
    with pytest.raises(ValueError):
        MeasureIn(day=date.today() + timedelta(days=1), kind="fungizid")
    with pytest.raises(ValueError):
        MeasureIn(day=date.today(), kind="duenger")
    with pytest.raises(ValueError):
        MeasureIn(day=date.today(), kind="fungizid", amount=2)          # Menge ohne Einheit


def test_measure_anlegen_und_liste():
    c = Conn(rows=[("m1",)])
    out = create_measure(c, "f1", MeasureIn(day=date.today(), kind="fungizid", product=" X "), "u1")
    assert out.id == "m1" and out.kindLabel == "Fungizid" and out.product == "X" and c.commits == 1
    assert "'pflanzenschutz'" in c.log[0][0]
    c2 = Conn(rows=[("m1", date(2026, 5, 2), "insektizid", None, None, None)])
    assert list_measures(c2, "f1", 2026)[0].kindLabel == "Insektizid"


def test_measure_loeschen_nur_eigener_betrieb():
    assert delete_measure(Conn(rowcount=1), "m1", "farm1") is True
    assert delete_measure(Conn(rowcount=0), "m1", "fremd") is False


# ---------- Brücke ----------

def test_gewichtetes_profil():
    p = weighted_profile([(0.75, 80, 60, 100), (0.25, 40, 60, None)])
    assert p["scores"] == {"water": 70.0, "soil": 60.0, "protection": 100.0}
    assert p["profileScore"] == 76.7
    assert weighted_profile([(1, 80, None, None)]) is None


def test_field_profile_aus_db():
    c = Conn(rows=[(0.6, 78.0, 57.0, 82.0, 2026, "AT-5"), (0.4, 70.0, 60.0, 90.0, 2026, "AT-5")])
    prof = field_profile(c, "9001234567890", date(2026, 10, 6))
    assert prof.verified and prof.fieldsCount == 2 and prof.scores["water"] == 74.8 and prof.region == "AT-5"
    assert field_profile(Conn(rows=[]), "9001234567890") is None


def test_event_validierung():
    ok = {"type": "compare_choice", "gtin": "9001234567890", "comparedWith": ["9009876543210"], "verified": True,
          "comparedVerified": [False], "category": "Mehl", "region": "AT-5", "week": "2026-W41"}
    DemandEventBatch(events=[ok])
    for bad in ({"region": "Salzburg"}, {"week": "41"}, {"comparedVerified": [False, True]}, {"gtin": "abc"}):
        with pytest.raises(ValueError):
            DemandEventIn(**{**ok, **bad})


def _choice(chosen, others, panel=False):
    return {"type": "compare_choice", "verified": chosen, "compared_verified": others, "panel": panel, "value": None}


def test_praeferenzrate_erst_ab_mindestanzahl():
    ev = [_choice(True, [False])] * (MIN_EVENTS - 1)
    assert preference_rate(ev) == (None, MIN_EVENTS - 1)
    ev = [_choice(True, [False])] * 15 + [_choice(False, [True])] * 5 + [_choice(True, [True])] * 10
    rate, n = preference_rate(ev)
    assert n == 20 and rate == 0.75             # gleiche Profile zählen nicht


def test_zahlungsbereitschaft_und_signal():
    ev = [{"type": "survey_wtp", "value": v, "panel": True} for v in [0, 5, 10, 10, 20] * 4]
    assert wtp_median(ev) == (10.0, 20)
    s = build_signal("Mehl", "AT-5", ev + [_choice(True, [False])])
    assert s.events == 21 and s.willingnessToPayMedian == 10.0 and s.preferenceRate is None and s.panelShare > 0.9


def test_iso_wochen():
    w = iso_weeks_back(date(2026, 1, 5), 2)
    assert w == ["2026-W02", "2026-W01"]
