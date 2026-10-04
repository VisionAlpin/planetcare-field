/* PlanetCare Field: Demo Daten für die Übersicht.
   Struktur = Antwort des geplanten Endpunkts GET /fields/{id}/overview?season=2026
   Alle Werte sind BEISPIELWERTE für die Demo. */

window.PCF_DEMO = {
  farm: { id: "farm-001", name: "Musterbetrieb Flachgau" },

  field: {
    id: "field-nord",
    name: "Schlag Nord",
    municipality: "Oberndorf",
    crop: "Winterweizen",
    season: 2026,
    // GeoJSON Polygon (WGS84, [lon, lat]); Fläche wird daraus berechnet
    geometry: {
      type: "Polygon",
      coordinates: [[
        [12.9372, 47.9461],
        [12.9418, 47.9466],
        [12.9431, 47.9442],
        [12.9405, 47.9428],
        [12.9366, 47.9436],
        [12.9372, 47.9461]
      ]]
    }
  },

  seasons: [2026, 2025],
  fields: [
    { id: "field-nord", name: "Schlag Nord" },
    { id: "field-sued", name: "Schlag Süd" }
  ],

  // Teilwerte 0 bis 100. available:false => "Noch keine Daten"
  scores: {
    water: {
      available: true,
      value: 78,
      previousSeason: 72,
      regionalAverage: 71,
      source: "Sentinel 2 + CDI",
      date: "2026-09-15",
      explanation: "Wie gut der Schlag Trockenphasen übersteht, gemessen an Dürrestufe (CDI) und Vegetationsverlauf im Vergleich zu Schlägen derselben Kultur im Bezirk."
    },
    soil: {
      available: true,
      value: 45,
      previousSeason: 48,
      regionalAverage: 52,
      source: "Sentinel 2 + SoilGrids",
      date: "2026-09-15",
      explanation: "Entwicklung der Bodengesundheit: Tage mit grüner Bodenbedeckung über das Jahr, Basiswerte aus SoilGrids und eingetragene Maßnahmen."
    },
    protection: {
      available: true,
      value: 63,
      previousSeason: 55,
      regionalAverage: 60,
      source: "ERA5 + Einträge",
      date: "2026-09-15",
      explanation: "Wie gezielt Pflanzenschutz eingesetzt wird: eingetragene Behandlungen im Verhältnis zu Tagen mit erhöhtem Krankheitsrisiko aus Wetterdaten (ERA5)."
    }
  },

  hint: {
    text: "Bodenfeuchte seit 14 Tagen unter regionalem Durchschnitt.",
    link: "#felder"
  },

  // Verlauf der Teilwerte in der Saison
  series: [
    { date: "2026-04-15", water: 70, soil: 47, protection: 58 },
    { date: "2026-05-01", water: 71, soil: 46, protection: 57 },
    { date: "2026-05-15", water: 73, soil: 46, protection: 59 },
    { date: "2026-06-01", water: 74, soil: 45, protection: 60 },
    { date: "2026-06-15", water: 72, soil: 44, protection: 61 },
    { date: "2026-07-01", water: 74, soil: 44, protection: 60 },
    { date: "2026-07-15", water: 75, soil: 45, protection: 62 },
    { date: "2026-08-01", water: 76, soil: 45, protection: 61 },
    { date: "2026-08-15", water: 77, soil: 44, protection: 62 },
    { date: "2026-09-01", water: 77, soil: 45, protection: 63 },
    { date: "2026-09-15", water: 78, soil: 45, protection: 63 }
  ],

  methodology: {
    version: "v1.0",
    computedAt: "2026-09-15",
    dataSources: ["Copernicus Sentinel 2", "EDO", "ERA5", "SoilGrids"]
  }
};
