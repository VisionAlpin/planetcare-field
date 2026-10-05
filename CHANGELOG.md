# Changelog

## 0.4.0 (5. Oktober 2026)

### Neu
- Nachtjob `pcf-jobs`: lädt je Schlag NDVI (Sentinel 2, Statistical API des CDSE, mit Wolkenmaske) und Tageswetter (ERA5-Land) und berechnet die Teilwerte alle 10 Tage seit Saisonbeginn.
- Teilwerte nach Konzept: Wasser (Vitalität in Trockenphasen), Boden (Tage mit grüner Bedeckung), Pflanzenschutz (gezielte Behandlungen bei Risikowetter).
- Tabellen `indicator_values`, `score_snapshots`, `job_runs`.
- `overview_queries.py`: Verlauf, Vorjahr und regionaler Vergleich aus den Stichtagen; `/health` mit letztem Joblauf.
- Werkzeug `set_field_geometry` mit Plausibilitätsprüfung (DACH, 0,5 bis 100 ha).
- Ein fehlerhafter Schlag stoppt den Lauf nicht; Exit Code 1 nur bei Totalausfall, damit Render benachrichtigt.
- 22 Tests (10 Job, 12 API).

### Enthalten
- Alle Änderungen aus 0.3.0.

## 0.3.0 (5. Oktober 2026)
- Fehlende Vergleichswerte werden ausgeblendet statt als 0 gerechnet; Quellen als Anzeigenamen; Verlauf nur aktuelle Saison; Hinweiszeile; „veraltet“ Markierung; Impressum und Datenschutz; Pydantic Schemas und Bearer Schema.
