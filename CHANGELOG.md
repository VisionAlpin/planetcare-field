# Changelog

## 0.3.0 (5. Oktober 2026)

### Behoben
- Fehlende Vergleichswerte wurden als 0 gerechnet („+78 zum Vorjahr“, „Region Ø 0“). Jetzt werden fehlende Werte ausgeblendet; das Backend liefert die Vorsaison mit.
- Technische Quellenschlüssel (z. B. `copernicus_gdo`) werden als Anzeigenamen gezeigt.
- Verlauf zeigt nur Messungen der aktuellen Saison; unter 3 Messungen ein erklärender Hinweis statt einer irreführenden Linie.
- Methodikversion einheitlich „v1.0“.

### Neu
- Hinweiszeile wird per Regel erzeugt, wenn das Backend keinen Hinweis liefert.
- Werte älter als 14 Tage sind als „veraltet“ gekennzeichnet.
- Fußzeile mit Impressum und Datenschutz.
- Frontend lädt live von der API, offline mit Demo Daten.
- Backend: `scoring.py` (Bewertung, Vorsaison, Region ab 3 Schlägen, Hinweis, Boden und Pflanzenschutz nach Konzept) und `schemas.py` (Pydantic Antwortmodelle, Bearer Schema für die Verbraucher App).
- 10 Tests für die Bewertungslogik.
