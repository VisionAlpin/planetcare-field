# PlanetCare Field — Go Live Anleitung
## GitHub → Render → field.planetcarescan.at
**Stand:** 04.10.2026 | **Frist:** 10. Oktober 2026

---

## Schritt 1: GitHub Repository anlegen

### 1.1 Repo erstellen

1. Öffne [github.com](https://github.com) und melde dich an
2. Klick oben rechts auf **+** → **New repository**
3. Einstellungen:
   - **Owner:** dein Account (oder VisionAlpin GmbH falls vorhanden)
   - **Repository name:** `planetcare-field`
   - **Visibility:** Public
   - **License:** Apache 2.0
   - **Add .gitignore:** keines auswählen (haben wir schon)
4. Klick **Create repository**

### 1.2 Code pushen

Öffne ein Terminal und führe diese Befehle aus:

```bash
cd /Users/seh/kDrive/04_Projekte/PlanetCareField

git init
git add .
git commit -m "feat: initial PlanetCare Field v0.2 — FastAPI + Render Blueprint"

# URL aus dem GitHub-Repo kopieren (Seite nach dem Erstellen):
git remote add origin https://github.com/DEIN-USERNAME/planetcare-field.git
git branch -M main
git push -u origin main
```

> Ersetze `DEIN-USERNAME` mit deinem GitHub-Benutzernamen.

**Kontrolle:** Öffne das Repo im Browser. Du solltest `api/`, `jobs/`, `web/`, `render.yaml` sehen. Keine `.env`-Datei drin — das ist wichtig.

---

## Schritt 2: Render einrichten

### 2.1 Render-Konto

Falls noch kein Konto: [render.com](https://render.com) → Sign up mit GitHub-Konto verbinden. Das erleichtert den Zugriff auf dein Repo.

### 2.2 Blueprint anlegen (alle 3 Dienste auf einmal)

1. Im Render-Dashboard: **New** → **Blueprint**
2. Repo `planetcare-field` auswählen → **Connect**
3. Render liest `render.yaml` und zeigt dir 3 Dienste:
   - `pcf-api` (Web Service, Docker, Frankfurt)
   - `pcf-jobs` (Cron Job, Docker, Frankfurt)
   - `pcf-db` (PostgreSQL 16, Frankfurt)
4. Klick **Apply**

### 2.3 Umgebungsvariablen eintragen

Nach dem Apply erscheinen die Dienste. Bei `pcf-api` und `pcf-jobs` fehlen noch 2 Werte (in `render.yaml` als `sync: false` markiert):

**Für pcf-api** → Settings → Environment:

| Variable | Wert |
|----------|------|
| `CDSE_CLIENT_ID` | *(kommt in Schritt 3)* |
| `CDSE_CLIENT_SECRET` | *(kommt in Schritt 3)* |

**Für pcf-jobs** dieselben Werte nochmal eintragen.

`SERVICE_API_KEY` und `SESSION_SECRET` werden von Render automatisch generiert — nichts tun.

### 2.4 Datenbankplan wählen

Im Blueprint-Dialog oder nachträglich unter `pcf-db` → Settings:
- **Nicht** den kostenlosen Plan nehmen (läuft nach 90 Tagen ab, keine Backups)
- Kleinsten **bezahlten** Plan wählen: **Starter** (~$7/Monat)

Gleiches gilt für `pcf-api`: kleinster bezahlter Plan **Starter** (~$7/Monat).  
`pcf-jobs` (Cron): **Free** reicht für den Nachtjob.

### 2.5 Erster Deploy abwarten

Render baut jetzt die Docker-Images. Das dauert beim ersten Mal 3–5 Minuten. Du siehst den Log live.

**Kontrolle:** Wenn der Deploy grün ist, öffne:
```
https://pcf-api.onrender.com/health
```
Antwort soll sein: `{"status":"ok","version":"0.2.0"}`

Wenn das klappt, hat Alembic die Datenbank angelegt und die Demo-Daten sind eingespielt.

**Demo prüfen:**
```
https://pcf-api.onrender.com/demo
```
Du solltest das Dashboard mit Musterbetrieb Flachgau sehen.

---

## Schritt 3: Copernicus-Zugänge holen

Diese braucht der Nachtjob für Satellitendaten. Kostenlos, aber Registrierung nötig.

### 3.1 Copernicus Data Space (CDSE) — für Sentinel-2

1. Öffne [dataspace.copernicus.eu](https://dataspace.copernicus.eu)
2. Klick **Register** → Konto mit E-Mail erstellen
3. Nach der Bestätigung: [Identity & Access Management](https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/auth?client_id=cdse-public)
4. Unter **User settings** → **OAuth clients** → **Create client**
   - Client ID: `planetcare-field`
   - Notiere `Client ID` und `Client Secret`
5. Diese Werte in Render bei `CDSE_CLIENT_ID` und `CDSE_CLIENT_SECRET` eintragen (pcf-api + pcf-jobs)

### 3.2 Copernicus Climate Data Store (ERA5) — für Wetterdaten

*(Erst für den 24. Oktober Meilenstein nötig — jetzt überspringen)*

---

## Schritt 4: Domain einrichten

### 4.1 CNAME-Eintrag setzen

In der Verwaltung von `planetcarescan.at` (wer ist der Domain-Anbieter?):

| Typ | Name | Ziel |
|-----|------|------|
| CNAME | `field` | `pcf-api.onrender.com` |

### 4.2 Custom Domain in Render eintragen

1. `pcf-api` → **Settings** → **Custom Domains**
2. Eintragen: `field.planetcarescan.at`
3. Render generiert automatisch ein HTTPS-Zertifikat (Let's Encrypt) — dauert 1–2 Minuten

**Kontrolle:**
```
https://field.planetcarescan.at/health
https://field.planetcarescan.at/demo
```

---

## Schritt 5: DPA mit Render abschließen

Render bietet einen Auftragsverarbeitungsvertrag (DSGVO) an:

1. `pcf-api` → **Settings** → ganz unten: **Data Processing Agreement**
2. Herunterladen, unterschreiben, an dich selbst weiterleiten
3. Im VisionAlpin-Ordner ablegen: `/Users/seh/kDrive/01_Beruf/VisionAlpin/Dokumente/DPA_Render_2026.pdf`

---

## Checkliste 10. Oktober

Hak ab sobald erledigt:

- [ ] Repo `planetcare-field` öffentlich auf GitHub, Apache 2.0, keine Credentials im Code
- [ ] Blueprint in Render angelegt, alle 3 Dienste (Frankfurt) laufen
- [ ] `/health` antwortet `{"status":"ok"}`
- [ ] Demo-Daten eingespielt (Musterbetrieb Flachgau, 2 Schläge)
- [ ] `/demo` zeigt das neue Dashboard mit echten DB-Daten
- [ ] CDSE-Zugangsdaten eingetragen

---

## Falls etwas schiefgeht

**Build-Fehler im Render-Log:**
- `libgdal-dev not found` → kein Problem, der apt-get-Befehl im Dockerfile ist drin
- `DATABASE_URL not set` → Blueprint nochmal prüfen, DB-Verknüpfung in render.yaml korrekt?

**Demo zeigt "Demo data not seeded yet":**
```bash
# Einmalig manuell ausführen — in Render unter pcf-api → Shell:
cd /app/api && python seed_demo.py
```

**Health-Check schlägt fehl:**
- Log von pcf-api aufmachen → Alembic-Fehler? → Migration-Datei prüfen

---

*Nächster Termin: 17. Oktober — Design-Korrektur + Domain + DPA*
