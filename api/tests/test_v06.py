"""Tests v0.6: Anmeldung, Overview aus der Datenbank, Nachtjob Abschluss.  Im Ordner api/:  python -m pytest -q"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import consume_token, hash_secret, login_mail, normalize_email, request_link, user_from_session  # noqa: E402
from app.overview import build_overview  # noqa: E402


class Cur:
    def __init__(self, conn): self.conn = conn
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def execute(self, sql, params=()):
        self.conn.log.append((" ".join(sql.split()), params))
        self.result = self.conn.respond(" ".join(sql.split()), params)
    def fetchone(self): return self.result[0] if self.result else None
    def fetchall(self): return self.result or []


class Conn:
    def __init__(self, respond): self.respond, self.log, self.commits = respond, [], 0
    def cursor(self): return Cur(self)
    def commit(self): self.commits += 1


# ---------- Anmeldung ----------

def test_email_normalisierung():
    assert normalize_email("  Landwirt@Beispiel.AT ") == "landwirt@beispiel.at"
    assert normalize_email("kein-at-zeichen") is None


def test_link_nur_fuer_bekannte_adresse_und_mit_limit():
    sent = []
    known = Conn(lambda sql, p: [("u1",)] if "FROM users" in sql else [(0,)] if "count(*)" in sql else [])
    request_link(known, "landwirt@beispiel.at", "https://pcf.test/", mailer=lambda *a: sent.append(a))
    assert len(sent) == 1 and "https://pcf.test/auth/callback?token=" in sent[0][2]
    token = sent[0][2].split("token=")[1].split()[0]
    insert = [l for l in known.log if l[0].startswith("INSERT INTO login_tokens")][0]
    assert insert[1][0] == hash_secret(token) and token not in json.dumps(str(insert))   # nur der Hash wird gespeichert

    unknown = Conn(lambda sql, p: [])
    request_link(unknown, "fremd@beispiel.at", "https://pcf.test", mailer=lambda *a: sent.append(a))
    limited = Conn(lambda sql, p: [("u1",)] if "FROM users" in sql else [(5,)] if "count(*)" in sql else [])
    request_link(limited, "landwirt@beispiel.at", "https://pcf.test", mailer=lambda *a: sent.append(a))
    assert len(sent) == 1


def test_link_einloesen_erzeugt_sitzung():
    c = Conn(lambda sql, p: [("u1",)] if sql.startswith("UPDATE login_tokens") else [])
    session = consume_token(c, "abc", "Browser")
    assert session and len(session) > 30
    assert any(l[0].startswith("INSERT INTO sessions") and l[1][0] == hash_secret(session) for l in c.log)
    assert consume_token(Conn(lambda sql, p: []), "abgelaufen") is None
    assert consume_token(c, "x" * 500) is None


def test_sitzung_zu_nutzer():
    c = Conn(lambda sql, p: [("u1", "farm1", "a@b.at", "farmer")])
    u = user_from_session(c, "s")
    assert u.farm_id == "farm1" and not u.is_demo
    assert user_from_session(c, None) is None


def test_mailtext():
    subj, body = login_mail("https://x/auth/callback?token=t")
    assert "15 Minuten" in body and "token=t" in body


# ---------- Overview aus der Datenbank ----------

GEOM = json.dumps({"type": "Polygon", "coordinates": [[[13.0, 47.9], [13.01, 47.9], [13.01, 47.91], [13.0, 47.9]]]})


def _overview_db(snapshots, prev=None, regional=()):
    def respond(sql, p):
        if sql.startswith("SELECT id::text FROM fields WHERE farm_id"):
            return [("f1",)]
        if "FROM fields f JOIN farms" in sql:
            return [("f1", "Schlag Nord", "Oberndorf", "Winterweizen", GEOM, 12.4, "AT-5", "farm1", "Musterbetrieb")] if p == ("f1", "farm1") else []
        if sql.startswith("SELECT id::text, name FROM fields"):
            return [("f1", "Schlag Nord"), ("f2", "Schlag Süd")]
        if sql.startswith("SELECT DISTINCT season"):
            return [(2026,), (2025,)]
        if sql.startswith("SELECT max(computed_at)"):
            return [(date(2026, 10, 6),)]
        if "ORDER BY asof DESC LIMIT 1" in sql:
            return [prev] if prev else []
        if "FROM score_snapshots WHERE field_id = %s AND season = %s ORDER BY asof" in sql:
            return snapshots
        if sql.startswith("WITH me AS"):
            return list(regional)
        return []
    return Conn(respond)


def test_overview_aus_snapshots():
    snaps = [(date(2026, 9, d), 70.0 + d / 10, 60.0, 90.0, {"water": "sentinel2_era5", "soil": "sentinel2", "protection": "era5_treatments"},
              {"water": "2026-09-28", "soil": "2026-09-28", "protection": "2026-09-30"}) for d in (1, 11, 21)]
    out = build_overview(_overview_db(snaps, prev=(74.0, 52.0, 79.0), regional=[(70, 60, 80), (72, 62, 82), (74, 64, 84)]), "default", 2026, "farm1", date(2026, 10, 6))
    s = out["scores"]
    assert s["water"]["source"] == "Sentinel 2 + ERA5" and s["protection"]["source"] == "ERA5 + Einträge"
    assert s["water"]["date"] == "2026-09-28" and s["water"]["previousSeason"] == 74.0 and s["soil"]["regionalAverage"] == 62
    assert len(out["series"]) == 3 and out["field"]["areaHa"] == 12.4 and out["field"]["regionCode"] == "AT-5"
    assert out["methodology"]["computedAt"] == "2026-10-06" and "Copernicus Sentinel 2" in out["methodology"]["dataSources"]


def test_overview_ohne_snapshots_zeigt_keine_alten_werte():
    out = build_overview(_overview_db([]), "f1", 2026, "farm1", date(2026, 10, 6))
    assert all(not out["scores"][k]["available"] for k in ("water", "soil", "protection"))
    assert out["total"] == {"available": False} and out["series"] == []


def test_overview_fremder_schlag():
    assert build_overview(_overview_db([]), "f1", 2026, "anderer_betrieb") is None


def test_overview_passt_zum_schema():
    from app.schemas import Overview
    snaps = [(date(2026, 9, 1), 70.0, 60.0, 90.0, {}, {})]
    Overview.model_validate(build_overview(_overview_db(snaps), "f1", 2026, "farm1", date(2026, 10, 6)))
