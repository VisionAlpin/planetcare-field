/* PlanetCare Field: Übersicht
   Rendert die Übersicht aus einem Datenobjekt (Struktur siehe data/demo-data.js).
   Ohne Framework, damit es sich in jeden Stack übertragen lässt. */

(function () {
  "use strict";

  /* ---------- Konfiguration ---------- */

  const SCORES = [
    { key: "water", label: "Wasser", icon: "droplet", color: "var(--series-water)", dash: "", legend: "solid" },
    { key: "soil", label: "Boden", icon: "layers", color: "var(--series-soil)", dash: "5 4", legend: "dashed" },
    { key: "protection", label: "Pflanzenschutz", icon: "shield-check", color: "var(--series-protection)", dash: "1.5 3.5", legend: "dotted" }
  ];

  // Bewertungsgrenzen laut Design Korrektur 1.5
  function rating(value) {
    if (value >= 70) return { cls: "good", text: "gut" };
    if (value >= 40) return { cls: "medium", text: "mittel" };
    return { cls: "critical", text: "kritisch" };
  }

  const MIN_SCORES_FOR_TOTAL = 2; // Gesamtwert erst ab zwei verfügbaren Teilwerten
  const STALE_DAYS = 14; // ältere Werte werden als "veraltet" gekennzeichnet

  // Anzeigenamen für technische Quellenschlüssel (Rückfall, falls das Backend Schlüssel liefert)
  const SOURCE_LABELS = {
    copernicus_edo: "Copernicus EDO (CDI)",
    copernicus_gdo: "Copernicus EDO (CDI)",
    edo_cdi: "Copernicus EDO (CDI)",
    sentinel2: "Sentinel 2",
    "sentinel-2": "Sentinel 2",
    era5: "ERA5",
    soilgrids: "SoilGrids",
    treatments: "Einträge",
    era5_treatments: "ERA5 + Einträge"
  };
  const MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

  /* ---------- Hilfsfunktionen ---------- */

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function fmtDate(iso) {
    const [y, m, d] = iso.split("-");
    return d + "." + m + "." + y;
  }

  function mean(values) {
    return values.reduce((a, b) => a + b, 0) / values.length;
  }

  // Zahl prüfen: null, undefined und NaN gelten als "kein Wert" (nie als 0 rechnen!)
  function isNum(v) {
    return typeof v === "number" && Number.isFinite(v);
  }

  // Mittelwert nur, wenn ALLE Werte vorhanden sind, sonst null
  function meanOrNull(values) {
    return values.length && values.every(isNum) ? mean(values) : null;
  }

  function sourceLabel(src) {
    if (!src) return "";
    return SOURCE_LABELS[String(src).toLowerCase()] || src;
  }

  function versionLabel(v) {
    if (!v) return "";
    return /^v/i.test(v) ? v : "v" + v;
  }

  function daysSince(iso) {
    return Math.floor((Date.now() - Date.parse(iso)) / 864e5);
  }

  // Fläche eines GeoJSON Polygons in Hektar (lokale Projektion, genau genug für Feldgrößen)
  function areaHa(geometry) {
    const ring = geometry.coordinates[0];
    const lat0 = mean(ring.map((p) => p[1])) * Math.PI / 180;
    const R = 6371008.8;
    const pts = ring.map(([lon, lat]) => [lon * Math.PI / 180 * R * Math.cos(lat0), lat * Math.PI / 180 * R]);
    let sum = 0;
    for (let i = 0; i < pts.length - 1; i++) sum += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1];
    return Math.abs(sum) / 2 / 10000;
  }

  // Gesamtwert = Mittelwert der verfügbaren Teilwerte (Backend bleibt maßgeblich, hier nur Anzeige)
  function computeTotal(scores) {
    const avail = SCORES.map((s) => scores[s.key]).filter((s) => s && s.available);
    if (avail.length < MIN_SCORES_FOR_TOTAL) return { available: false };
    const dates = avail.map((s) => s.date).sort();
    return {
      available: true,
      value: mean(avail.map((s) => s.value)),
      previousSeason: meanOrNull(avail.map((s) => s.previousSeason)),
      regionalAverage: meanOrNull(avail.map((s) => s.regionalAverage)),
      source: "Methodik",
      date: dates[dates.length - 1],
      explanation: "Mittelwert der verfügbaren Teilwerte Wasser, Boden und Pflanzenschutz. Wird erst ab zwei Teilwerten berechnet."
    };
  }

  /* ---------- Bausteine ---------- */

  function kpiTile({ id, label, iconName, data, total, methodVersion }) {
    const popId = "pop-" + id;
    const stale = !total && data.available && data.date && daysSince(data.date) > STALE_DAYS;
    const sourceLine = total ? "Methodik " + versionLabel(methodVersion) : data.available ? sourceLabel(data.source) + " · " + fmtDate(data.date) : "";

    let body;
    if (!data.available) {
      body =
        '<div class="kpi-empty">Noch keine Daten</div>' +
        (id === "protection" ? '<div class="kpi-compare"><a href="#behandlungen">Behandlungen eintragen</a></div>' : "");
    } else {
      const v = Math.round(data.value);
      const r = rating(v);
      const parts = [];
      if (isNum(data.previousSeason)) {
        const delta = Math.round(data.value - data.previousSeason);
        const trendIcon = delta > 0 ? "trending-up" : delta < 0 ? "trending-down" : "minus";
        const deltaText = (delta > 0 ? "+" : delta < 0 ? "−" : "±") + Math.abs(delta);
        parts.push('<span class="delta">' + icon(trendIcon) + deltaText + " zum Vorjahr</span>");
      }
      if (isNum(data.regionalAverage)) {
        parts.push("<span>Region Ø " + Math.round(data.regionalAverage) + "</span>");
      }
      body =
        '<div class="kpi-value-row"><span class="kpi-value num">' + v + '</span><span class="kpi-max">/ 100</span></div>' +
        '<div class="kpi-status status--' + r.cls + '"><span class="dot" aria-hidden="true"></span>' + r.text + "</div>" +
        (parts.length
          ? '<div class="kpi-compare num">' + parts.join('<span class="sep" aria-hidden="true">|</span>') + "</div>"
          : '<div class="kpi-compare">Noch keine Vergleichswerte</div>');
    }

    const popSource = data.available
      ? total
        ? "Methodik " + versionLabel(methodVersion)
        : sourceLabel(data.source) + " · Stand " + fmtDate(data.date) + (stale ? " (älter als " + STALE_DAYS + " Tage)" : "")
      : "Für diesen Teilwert liegen noch keine Daten vor.";

    return (
      '<article class="kpi' + (total ? " kpi--total" : "") + '" aria-labelledby="lbl-' + id + '">' +
      '<div class="kpi-head">' + icon(iconName) +
      '<span id="lbl-' + id + '">' + esc(label) + "</span>" +
      '<button class="icon-button info-btn" type="button" aria-label="Erklärung zu ' + esc(label) + '" aria-expanded="false" aria-controls="' + popId + '">' + icon("info") + "</button>" +
      "</div>" +
      body +
      (sourceLine ? '<div class="kpi-source' + (stale ? " is-stale" : "") + '">' + esc(sourceLine) + (stale ? ' <span class="stale-tag">veraltet</span>' : "") + "</div>" : "") +
      '<div class="popover" id="' + popId + '" role="dialog" aria-label="' + esc(label) + '" hidden>' +
      "<p>" + esc(data.explanation || "") + "</p>" +
      "<p>" + esc(popSource) + "</p>" +
      "</div>" +
      "</article>"
    );
  }

  function renderKpis(el, d) {
    // Gesamtwert vom Backend bevorzugen, sonst lokal berechnen
    const local = computeTotal(d.scores);
    const total = d.total && d.total.available && local.available ? Object.assign({}, local, d.total) : local;
    let html = kpiTile({ id: "total", label: "Gesamt", iconName: "gauge", data: total, total: true, methodVersion: d.methodology.version });
    SCORES.forEach((s) => {
      html += kpiTile({ id: s.key, label: s.label, iconName: s.icon, data: d.scores[s.key] });
    });
    el.innerHTML = html;
  }

  function wirePopovers(root) {
    root.addEventListener("click", (e) => {
      const btn = e.target.closest(".info-btn");
      root.querySelectorAll(".info-btn[aria-expanded='true']").forEach((b) => {
        if (b !== btn) toggle(b, false);
      });
      if (btn) {
        e.preventDefault();
        toggle(btn, btn.getAttribute("aria-expanded") !== "true");
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") root.querySelectorAll(".info-btn[aria-expanded='true']").forEach((b) => toggle(b, false));
    });
    document.addEventListener("click", (e) => {
      if (!root.contains(e.target)) root.querySelectorAll(".info-btn[aria-expanded='true']").forEach((b) => toggle(b, false));
    });
    function toggle(btn, open) {
      btn.setAttribute("aria-expanded", String(open));
      document.getElementById(btn.getAttribute("aria-controls")).hidden = !open;
    }
  }

  /* ---------- Verlaufsdiagramm ---------- */

  function renderChart(wrap, d) {
    const scoresAvail = SCORES.filter((s) => d.scores[s.key] && d.scores[s.key].available);
    const season = String(d.field.season);
    // Nur Messungen DIESER Saison, zeitlich sortiert (Vorjahreswerte gehören in previousSeason)
    const rows = (d.series || [])
      .filter((r) => r && r.date && String(r.date).slice(0, 4) === season)
      .sort((a, b) => Date.parse(a.date) - Date.parse(b.date))
      .map((r) => {
        const vals = scoresAvail.map((s) => r[s.key]).filter(isNum);
        return Object.assign({}, r, { total: vals.length >= MIN_SCORES_FOR_TOTAL ? mean(vals) : null });
      });

    const box = wrap.querySelector(".chart-wrap");
    const legendEl = wrap.querySelector(".legend");
    const toggle = wrap.querySelector(".table-toggle");
    if (rows.length < 3) {
      legendEl.innerHTML = "";
      toggle.hidden = true;
      wrap.querySelector(".data-table").hidden = true;
      box.innerHTML =
        '<div class="chart-empty">Für einen Verlauf braucht es mindestens drei Messungen in dieser Saison. ' +
        "Bisher liegen " + rows.length + " vor. Neue Werte kommen mit jeder wolkenfreien Satellitenaufnahme dazu.</div>";
      return;
    }
    toggle.hidden = false;
    const series = [{ key: "total", label: "Gesamt", color: "var(--brand)", dash: "", width: 2.5, isTotal: true }].concat(
      scoresAvail.map((s) => ({ key: s.key, label: s.label, color: s.color, dash: s.dash, legend: s.legend, width: 1.5 }))
    );

    // Legende
    legendEl.innerHTML = series
      .map((s) => '<span class="legend-item"><span class="legend-swatch" style="border-top-color:' + s.color + ";border-top-width:" + s.width + "px;" + "border-top-style:" + (s.legend || "solid") + ";" + '"></span>' + esc(s.label) + "</span>")
      .join("");

    const W = Math.max(box.clientWidth, 280);
    const H = 220;
    const pad = { l: 32, r: 116, t: 10, b: 26 };
    const t = (iso) => Date.parse(iso);
    const t0 = t(rows[0].date);
    const t1 = t(rows[rows.length - 1].date);
    const X = (iso) => pad.l + ((t(iso) - t0) / (t1 - t0)) * (W - pad.l - pad.r);
    const Y = (v) => pad.t + (1 - v / 100) * (H - pad.t - pad.b);

    let svg = '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Verlauf der Teilwerte in der Saison ' + d.field.season + '">';

    // Raster 0, 25, 50, 75, 100
    [0, 25, 50, 75, 100].forEach((v) => {
      svg += '<line x1="' + pad.l + '" x2="' + (W - pad.r) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" stroke="' + (v === 0 ? "var(--border)" : "var(--grid)") + '" />';
      svg += '<text x="' + (pad.l - 8) + '" y="' + (Y(v) + 4) + '" text-anchor="end" class="num">' + v + "</text>";
    });

    // Monatsbeschriftung am Monatsersten
    const first = new Date(t0);
    for (let m = first.getUTCMonth() + (first.getUTCDate() > 1 ? 1 : 0); ; m++) {
      const iso = new Date(Date.UTC(first.getUTCFullYear(), m, 1)).toISOString().slice(0, 10);
      if (t(iso) > t1) break;
      svg += '<text x="' + X(iso) + '" y="' + (H - 6) + '" text-anchor="middle">' + MONTHS[Number(iso.slice(5, 7)) - 1] + "</text>";
    }

    // Linien, Gesamt zuletzt (oben)
    series.slice().reverse().forEach((s) => {
      const pts = rows.filter((r) => isNum(r[s.key])).map((r) => X(r.date).toFixed(1) + "," + Y(r[s.key]).toFixed(1)).join(" ");
      svg += '<polyline points="' + pts + '" fill="none" stroke="' + s.color + '" stroke-width="' + s.width + '" stroke-linecap="round" stroke-linejoin="round"' + (s.dash ? ' stroke-dasharray="' + s.dash + '"' : "") + " />";
    });

    // Direkte Beschriftung am Linienende, Überlappung vermeiden
    const last = rows[rows.length - 1];
    const labels = series
      .filter((s) => isNum(last[s.key]))
      .map((s) => ({ s, y: Y(last[s.key]), text: s.label + " " + Math.round(last[s.key]) }))
      .sort((a, b) => a.y - b.y);
    const GAP = 14;
    for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < GAP) labels[i].y = labels[i - 1].y + GAP;
    const overflow = labels.length ? labels[labels.length - 1].y - (H - pad.b) : 0;
    if (overflow > 0) labels.forEach((l) => (l.y -= overflow));
    labels.forEach((l) => {
      svg += '<text x="' + (W - pad.r + 8) + '" y="' + (l.y + 4) + '" class="num ' + (l.s.isTotal ? "lbl-total" : "lbl-series") + '">' + esc(l.text) + "</text>";
    });

    // Hover Ebene
    svg += '<line class="crosshair" x1="0" x2="0" y1="' + pad.t + '" y2="' + (H - pad.b) + '" stroke="var(--text-muted)" stroke-width="1" visibility="hidden" />';
    svg += '<g class="hover-dots"></g>';
    svg += '<rect class="hit" x="' + pad.l + '" y="0" width="' + (W - pad.l - pad.r) + '" height="' + H + '" fill="transparent" />';
    svg += "</svg>";

    box.innerHTML = svg + '<div class="tooltip" hidden></div>';

    const svgEl = box.querySelector("svg");
    const cross = svgEl.querySelector(".crosshair");
    const dots = svgEl.querySelector(".hover-dots");
    const tip = box.querySelector(".tooltip");

    function show(clientX) {
      const rect = svgEl.getBoundingClientRect();
      const x = ((clientX - rect.left) / rect.width) * W;
      let best = 0;
      rows.forEach((r, i) => {
        if (Math.abs(X(r.date) - x) < Math.abs(X(rows[best].date) - x)) best = i;
      });
      const r = rows[best];
      const px = X(r.date);
      cross.setAttribute("x1", px);
      cross.setAttribute("x2", px);
      cross.setAttribute("visibility", "visible");
      dots.innerHTML = series
        .filter((s) => isNum(r[s.key]))
        .map((s) => '<circle cx="' + px + '" cy="' + Y(r[s.key]) + '" r="4" fill="' + s.color + '" stroke="var(--bg)" stroke-width="2" />')
        .join("");
      tip.innerHTML =
        '<div class="tooltip-date">' + fmtDate(r.date) + "</div>" +
        series.filter((s) => isNum(r[s.key])).map((s) => '<div class="tooltip-row"><span>' + esc(s.label) + '</span><strong class="num">' + Math.round(r[s.key]) + "</strong></div>").join("");
      tip.hidden = false;
      const scale = rect.width / W;
      const tipW = tip.offsetWidth;
      const right = px * scale + 12;
      tip.style.left = (right + tipW > rect.width ? px * scale - 12 - tipW : right) + "px";
      tip.style.top = pad.t * scale + "px";
    }
    function hide() {
      cross.setAttribute("visibility", "hidden");
      dots.innerHTML = "";
      tip.hidden = true;
    }
    const hit = svgEl.querySelector(".hit");
    hit.addEventListener("mousemove", (e) => show(e.clientX));
    hit.addEventListener("mouseleave", hide);
    hit.addEventListener("touchstart", (e) => show(e.touches[0].clientX), { passive: true });
    hit.addEventListener("touchmove", (e) => show(e.touches[0].clientX), { passive: true });
    hit.addEventListener("touchend", hide);

    // Tabellenansicht (Barrierefreiheit)
    const table = wrap.querySelector(".data-table");
    table.innerHTML =
      "<thead><tr><th>Datum</th>" + series.map((s) => "<th>" + esc(s.label) + "</th>").join("") + "</tr></thead>" +
      "<tbody>" + rows.map((r) => "<tr><td>" + fmtDate(r.date) + "</td>" + series.map((s) => '<td class="num">' + (isNum(r[s.key]) ? Math.round(r[s.key]) : "") + "</td>").join("") + "</tr>").join("") + "</tbody>";
  }

  /* ---------- Kartenausschnitt ---------- */

  function renderMap(el, geometry) {
    const ring = geometry.coordinates[0];
    const lat0 = mean(ring.map((p) => p[1])) * Math.PI / 180;
    const pts = ring.map(([lon, lat]) => [lon * Math.cos(lat0), -lat]);
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const s = Math.min(100 / (maxX - minX), 75 / (maxY - minY));
    const ox = (100 - (maxX - minX) * s) / 2, oy = (75 - (maxY - minY) * s) / 2;
    const poly = pts.map((p) => ((p[0] - minX) * s + ox).toFixed(2) + "," + ((p[1] - minY) * s + oy).toFixed(2)).join(" ");
    el.innerHTML =
      '<svg viewBox="-4 -4 108 83" role="img" aria-label="Umriss des Schlags">' +
      '<polygon points="' + poly + '" fill="var(--brand)" fill-opacity="0.12" stroke="var(--brand)" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke" />' +
      "</svg>";
  }

  /* ---------- Hinweis ---------- */

  // Rückfall, solange das Backend noch keinen Hinweis liefert:
  // der Teilwert mit dem größten Abstand UNTER dem regionalen Durchschnitt,
  // ohne Regionalwerte der schwächste Teilwert unter 70.
  function deriveHint(scores) {
    const avail = SCORES.map((s) => Object.assign({ label: s.label }, scores[s.key] || {})).filter((s) => s.available && isNum(s.value));
    const gaps = avail.filter((s) => isNum(s.regionalAverage) && s.value < s.regionalAverage);
    if (gaps.length) {
      const g = gaps.sort((a, b) => (a.value - a.regionalAverage) - (b.value - b.regionalAverage))[0];
      return { text: g.label + " liegt mit " + Math.round(g.value) + " um " + Math.round(g.regionalAverage - g.value) + " Punkte unter dem regionalen Durchschnitt.", link: "#felder" };
    }
    const weak = avail.filter((s) => s.value < 70).sort((a, b) => a.value - b.value)[0];
    if (weak) return { text: weak.label + " ist mit " + Math.round(weak.value) + " der schwächste Teilwert. Hier liegt das größte Verbesserungspotenzial.", link: "#felder" };
    return null;
  }

  /* ---------- Gesamte Seite ---------- */

  function renderOverview(d) {
    const ha = areaHa(d.field.geometry).toLocaleString("de-AT", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

    document.querySelector("[data-farm-name]").textContent = d.farm.name;
    document.querySelector("[data-field-name]").textContent = d.field.name;
    document.querySelector("[data-field-meta]").textContent = [d.field.municipality, d.field.crop, ha + " ha", "Saison " + d.field.season].join(" · ");

    const sel = document.querySelector("[data-field-select]");
    sel.innerHTML = d.fields.flatMap((f) => d.seasons.map((y) => '<option value="' + esc(f.id + ":" + y) + '"' + (f.id === d.field.id && y === d.field.season ? " selected" : "") + ">" + esc(f.name + " · " + y) + "</option>")).join("");

    const kpis = document.querySelector("[data-kpis]");
    renderKpis(kpis, d);
    wirePopovers(kpis);

    const hint = document.querySelector("[data-hint]");
    const h = d.hint && d.hint.text ? d.hint : deriveHint(d.scores);
    if (h) {
      hint.innerHTML = icon("info") + '<span class="hint-text"><span class="hint-label">Hinweis:</span> ' + esc(h.text) + "</span>" + (h.link ? '<a href="' + esc(h.link) + '">Details</a>' : "");
    } else {
      hint.remove();
    }

    const chartPanel = document.querySelector("[data-chart]");
    chartPanel.querySelector("[data-chart-title]").textContent = "Verlauf Saison " + d.field.season;
    const draw = () => renderChart(chartPanel, d);
    draw();
    let raf;
    window.addEventListener("resize", () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(draw);
    });
    const toggleBtn = chartPanel.querySelector(".table-toggle");
    const table = chartPanel.querySelector(".data-table");
    toggleBtn.addEventListener("click", () => {
      table.hidden = !table.hidden;
      toggleBtn.textContent = table.hidden ? "Als Tabelle anzeigen" : "Tabelle ausblenden";
      toggleBtn.setAttribute("aria-expanded", String(!table.hidden));
    });

    renderMap(document.querySelector("[data-map]"), d.field.geometry);
    document.querySelector("[data-map-name]").textContent = d.field.name;
    document.querySelector("[data-map-area]").textContent = ha + " ha";

    document.querySelector("[data-footer]").textContent =
      "Methodik " + versionLabel(d.methodology.version) + " · berechnet am " + fmtDate(d.methodology.computedAt) + " · Daten: " + d.methodology.dataSources.join(", ");
  }

  /* ---------- Daten laden ---------- */

  // Lädt die Übersicht von der API. Ohne Server (Datei geöffnet) oder mit ?offline werden die Demo Daten genutzt.
  async function loadOverview({ fieldId, season, demoData }) {
    const offline = !location.protocol.startsWith("http") || new URLSearchParams(location.search).has("offline");
    if (offline) return demoData;
    const res = await fetch("/api/fields/" + encodeURIComponent(fieldId) + "/overview?season=" + encodeURIComponent(season), {
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    if (res.status === 401) {
      location.href = "/login";
      return null;
    }
    if (!res.ok) throw new Error("Overview " + res.status);
    return res.json();
  }

  window.PlanetCareField = { renderOverview, loadOverview, computeTotal, rating, areaHa, deriveHint, VERSION: "0.3.0" };
})();
