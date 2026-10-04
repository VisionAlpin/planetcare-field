/* PlanetCare Field — Frontend App (Redesign) */

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : 'https://field.planetcarescan.app';

const params = new URLSearchParams(location.search);
const DEMO = params.get('demo') === '1';
const FIELD_ID = params.get('field') || null;

// ── Demo Data ───────────────────────────────────────────────────────────────
const DEMO_DATA = {
  farm: { name: "Musterbetrieb Flachgau", region: "Salzburg-Umgebung" },
  field: { name: "Schlag Nord", subtitle: "Oberndorf · Winterweizen · 12,4 ha · Saison 2026" },
  profile: {
    score_total: 72,
    score_water: 78,
    score_biodiversity: 57,   // heißt jetzt "Boden"
    score_pesticide: 82,      // MUSS einen Wert haben
    method_version: "1.0",
    calculated_at: "2026-09-15"
  },
  comparisons: {
    water:        { prev_year: 74, region_avg: 71, source: "Sentinel-2", date: "15.09.2026" },
    biodiversity: { prev_year: 52, region_avg: 61, source: "Sentinel-2", date: "15.09.2026" },
    pesticide:    { prev_year: 79, region_avg: 68, source: "Manual",     date: "01.07.2026" },
    total:        { prev_year: 68, region_avg: 67, source: "Methodik v1.0", date: "15.09.2026" }
  },
  trend: [
    { month: "Okt 25", water: 62, soil: 44, pest: 75, total: 60 },
    { month: "Dez 25", water: 58, soil: 46, pest: 75, total: 60 },
    { month: "Feb 26", water: 65, soil: 49, pest: 79, total: 64 },
    { month: "Apr 26", water: 71, soil: 53, pest: 81, total: 68 },
    { month: "Jun 26", water: 75, soil: 55, pest: 82, total: 71 },
    { month: "Sep 26", water: 78, soil: 57, pest: 82, total: 72 }
  ],
  demand: { preference_rate: 0.68, willingness_pct: 12, n_events: 25, trend: "+3%", is_panel: true }
};

// ── Info Texts ──────────────────────────────────────────────────────────────
const INFO = {
  total: {
    title: "Gesamt-Score",
    text: "Der Gesamt-Score aggregiert die drei Teilwerte Wasser, Boden und Pflanzenschutz nach Methodik v1.0."
  },
  water: {
    title: "Wasser-Score",
    text: "Berechnet aus NDVI-Mittelwert (Vegetationsgesundheit) und dem Combined Drought Indicator (CDI) des Copernicus Emergency Management Service. Datenquelle: Sentinel-2 (ESA), CDI (EU Copernicus)."
  },
  bio: {
    title: "Boden-Score",
    text: "Abgeleitet aus der räumlichen Variabilität des NDVI (Standardabweichung). Höhere Heterogenität der Vegetation korreliert mit höherer Bodenqualität. Datenquelle: Sentinel-2 L2A."
  },
  pest: {
    title: "Pflanzenschutz-Score",
    text: "Basiert auf Angaben zum Pestizideinsatz (kg Wirkstoff/ha). Berechnung: Score = 100 − (Einsatz × Faktor). Datenquelle: Manuelle Eingabe."
  }
};

// ── Helpers ─────────────────────────────────────────────────────────────────
function ratingLabel(score) {
  if (score == null) return { text: '', color: '' };
  if (score > 80) return { text: 'Sehr gut', color: 'var(--status-good)' };
  if (score >= 60) return { text: 'Gut',     color: 'var(--status-good)' };
  if (score >= 40) return { text: 'Mittel',  color: 'var(--status-mid)' };
  return             { text: 'Schwach',       color: 'var(--status-bad)' };
}

function setCard(ids, score, comp) {
  const { valueEl, compEl, sourceEl, ratingEl } = ids;

  if (score == null) {
    valueEl.innerHTML = '<span class="card-unavailable">Noch keine Daten<a href="#">Behandlungen eintragen</a></span>';
    compEl.textContent = '';
    sourceEl.querySelector('span').textContent = '';
    ratingEl.innerHTML = '';
    return;
  }

  valueEl.querySelector('.value-number').textContent = Math.round(score);

  const { text, color } = ratingLabel(score);
  ratingEl.innerHTML = `<span class="rating-dot" style="background:${color}"></span><span>${text}</span>`;

  if (comp) {
    compEl.textContent = `Vorjahr: ${comp.prev_year} · Region Ø: ${comp.region_avg}`;
    sourceEl.querySelector('span').textContent = `${comp.source} · ${comp.date}`;
  }
}

// ── Tab Navigation ──────────────────────────────────────────────────────────
// Wrap tab buttons in inner div for layout
document.addEventListener('DOMContentLoaded', () => {
  const tabBar = document.getElementById('tabBar');
  const inner = document.createElement('div');
  inner.className = 'tab-bar-inner';
  while (tabBar.firstChild) inner.appendChild(tabBar.firstChild);
  tabBar.appendChild(inner);
});

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
  });
});

// ── Info Modal ──────────────────────────────────────────────────────────────
document.querySelectorAll('.info-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const key = btn.dataset.info;
    document.getElementById('modalTitle').textContent = INFO[key]?.title || '';
    document.getElementById('modalText').textContent  = INFO[key]?.text  || '';
    document.getElementById('infoModal').style.display = 'flex';
  });
});
document.getElementById('modalClose').addEventListener('click', () => {
  document.getElementById('infoModal').style.display = 'none';
});
document.getElementById('infoModal').addEventListener('click', e => {
  if (e.target === e.currentTarget) e.currentTarget.style.display = 'none';
});

// ── Render Overview ─────────────────────────────────────────────────────────
function renderOverview(data) {
  const { farm, field, profile, comparisons } = data;

  // Header farm name
  const farmNameEl = document.getElementById('headerFarmName');
  if (farmNameEl) farmNameEl.textContent = farm?.name || '';

  // Page title
  const fieldTitleEl = document.getElementById('fieldTitle');
  const fieldSubEl = document.getElementById('fieldSubtitle');
  if (fieldTitleEl) fieldTitleEl.textContent = field?.name || 'Schlag Nord';
  if (fieldSubEl) fieldSubEl.textContent = field?.subtitle || '';

  // Footer
  const footerEl = document.getElementById('pageFooter');
  if (footerEl && profile) {
    footerEl.textContent = `Methodik v${profile.method_version || '1.0'} · berechnet am ${profile.calculated_at || '–'} · Daten: Copernicus Sentinel-2, EDO, ERA5`;
  }

  // Helper to build card element refs
  function cardRefs(suffix) {
    return {
      valueEl:  document.getElementById(`scoreCard${suffix}`),
      compEl:   document.getElementById(`comp${suffix}`),
      sourceEl: document.getElementById(`source${suffix}`),
      ratingEl: document.getElementById(`rating${suffix}`)
    };
  }

  // Total card
  setCard(
    { valueEl: document.getElementById('cardTotal'), compEl: document.getElementById('compTotal'), sourceEl: document.getElementById('sourceTotal'), ratingEl: document.getElementById('ratingTotal') },
    profile?.score_total,
    comparisons?.total
  );
  // Use the value-number span directly
  const totalNum = document.getElementById('scoreTotal');
  if (totalNum && profile?.score_total != null) totalNum.textContent = Math.round(profile.score_total);
  const ratingTotal = ratingLabel(profile?.score_total);
  const ratingTotalEl = document.getElementById('ratingTotal');
  if (ratingTotalEl && profile?.score_total != null) {
    ratingTotalEl.innerHTML = `<span class="rating-dot" style="background:${ratingTotal.color}"></span><span>${ratingTotal.text}</span>`;
  }
  const compTotal = document.getElementById('compTotal');
  if (compTotal && comparisons?.total) compTotal.textContent = `Vorjahr: ${comparisons.total.prev_year} · Region Ø: ${comparisons.total.region_avg}`;
  const stTotal = document.getElementById('sourceTextTotal');
  if (stTotal && comparisons?.total) stTotal.textContent = `${comparisons.total.source} · ${comparisons.total.date}`;

  // Water card
  const waterNum = document.getElementById('scoreWater');
  if (waterNum && profile?.score_water != null) waterNum.textContent = Math.round(profile.score_water);
  const ratingWater = ratingLabel(profile?.score_water);
  const ratingWaterEl = document.getElementById('ratingWater');
  if (ratingWaterEl && profile?.score_water != null) {
    ratingWaterEl.innerHTML = `<span class="rating-dot" style="background:${ratingWater.color}"></span><span>${ratingWater.text}</span>`;
  }
  const compWater = document.getElementById('compWater');
  if (compWater && comparisons?.water) compWater.textContent = `Vorjahr: ${comparisons.water.prev_year} · Region Ø: ${comparisons.water.region_avg}`;
  const stWater = document.getElementById('sourceTextWater');
  if (stWater && comparisons?.water) stWater.textContent = `${comparisons.water.source} · ${comparisons.water.date}`;

  // Boden card
  const bioNum = document.getElementById('scoreBio');
  if (bioNum && profile?.score_biodiversity != null) bioNum.textContent = Math.round(profile.score_biodiversity);
  const ratingBio = ratingLabel(profile?.score_biodiversity);
  const ratingBioEl = document.getElementById('ratingBio');
  if (ratingBioEl && profile?.score_biodiversity != null) {
    ratingBioEl.innerHTML = `<span class="rating-dot" style="background:${ratingBio.color}"></span><span>${ratingBio.text}</span>`;
  }
  const compBio = document.getElementById('compBio');
  if (compBio && comparisons?.biodiversity) compBio.textContent = `Vorjahr: ${comparisons.biodiversity.prev_year} · Region Ø: ${comparisons.biodiversity.region_avg}`;
  const stBio = document.getElementById('sourceTextBio');
  if (stBio && comparisons?.biodiversity) stBio.textContent = `${comparisons.biodiversity.source} · ${comparisons.biodiversity.date}`;

  // Pflanzenschutz card
  const pestNum = document.getElementById('scorePest');
  if (pestNum && profile?.score_pesticide != null) {
    pestNum.textContent = Math.round(profile.score_pesticide);
  } else if (pestNum) {
    // Unavailable
    const cardPest = document.getElementById('cardPest');
    const valDiv = cardPest.querySelector('.card-value');
    valDiv.innerHTML = '<span class="card-unavailable">Noch keine Daten<a href="#">Behandlungen eintragen</a></span>';
  }
  if (profile?.score_pesticide != null) {
    const ratingPest = ratingLabel(profile.score_pesticide);
    const ratingPestEl = document.getElementById('ratingPest');
    if (ratingPestEl) ratingPestEl.innerHTML = `<span class="rating-dot" style="background:${ratingPest.color}"></span><span>${ratingPest.text}</span>`;
    const compPest = document.getElementById('compPest');
    if (compPest && comparisons?.pesticide) compPest.textContent = `Vorjahr: ${comparisons.pesticide.prev_year} · Region Ø: ${comparisons.pesticide.region_avg}`;
    const stPest = document.getElementById('sourceTextPest');
    if (stPest && comparisons?.pesticide) stPest.textContent = `${comparisons.pesticide.source} · ${comparisons.pesticide.date}`;
  }
}

// ── Trend Chart (pure SVG) ───────────────────────────────────────────────────
function renderTrendChart(trendData) {
  const svg = document.getElementById('trendChart');
  if (!svg || !trendData || !trendData.length) return;

  const W = 560, H = 200;
  const padL = 32, padR = 16, padT = 16, padB = 36;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const n = trendData.length;

  function xPos(i) { return padL + (i / (n - 1)) * chartW; }
  function yPos(v) { return padT + chartH - (v / 100) * chartH; }

  function makePath(key, color, strokeW) {
    const pts = trendData.map((d, i) => `${xPos(i)},${yPos(d[key])}`).join(' ');
    const poly = trendData.map((d, i) => (i === 0 ? 'M' : 'L') + `${xPos(i)} ${yPos(d[key])}`).join(' ');
    return `<path d="${poly}" fill="none" stroke="${color}" stroke-width="${strokeW}" stroke-linejoin="round" stroke-linecap="round"/>`;
  }

  // Y-axis grid lines
  let gridLines = '';
  [0, 25, 50, 75, 100].forEach(v => {
    const y = yPos(v);
    gridLines += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--border)" stroke-width="1"/>`;
    gridLines += `<text x="${padL - 4}" y="${y + 4}" font-size="10" fill="var(--text-muted)" text-anchor="end" font-family="Inter,sans-serif">${v}</text>`;
  });

  // X-axis labels
  let xLabels = '';
  trendData.forEach((d, i) => {
    const x = xPos(i);
    const y = H - padB + 16;
    xLabels += `<text x="${x}" y="${y}" font-size="10" fill="var(--text-muted)" text-anchor="middle" font-family="Inter,sans-serif">${d.month}</text>`;
  });

  // Lines
  const lines = [
    makePath('water', '#9CA3AF', 1.5),
    makePath('soil',  '#6B7280', 1.5),
    makePath('pest',  '#374151', 1.5),
    makePath('total', 'var(--brand)', 2),
  ].join('');

  svg.innerHTML = gridLines + xLabels + lines;
}

// ── Load Overview ───────────────────────────────────────────────────────────
async function loadOverview() {
  if (DEMO) {
    document.getElementById('demoBadge').style.display = '';
    renderOverview(DEMO_DATA);
    renderTrendChart(DEMO_DATA.trend);
    return;
  }
  if (!FIELD_ID) {
    document.getElementById('fieldTitle').textContent = 'Kein Schlag-Parameter (?field=ID) angegeben';
    return;
  }
  try {
    const token = localStorage.getItem('pcf_token') || '';
    const r = await fetch(`${API_BASE}/fields/${FIELD_ID}/profile`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    renderOverview({
      farm:  { name: data.field_id },
      field: { name: data.field_id, subtitle: '' },
      profile: data.profile,
      comparisons: {}
    });
  } catch (e) {
    document.getElementById('fieldTitle').textContent = `Fehler: ${e.message}`;
  }
}

// ── Market Signals ───────────────────────────────────────────────────────────
async function loadMarket() {
  if (DEMO) { renderMarket(DEMO_DATA.demand); return; }
  try {
    const r = await fetch(`${API_BASE}/demand-signal/summary`);
    const data = await r.json();
    const first = data.summary?.[0];
    if (first) {
      renderMarket({
        preference_rate: first.preference_rate,
        willingness_pct: first.willingness_to_pay_pct_median,
        n_events: first.n_events,
        is_panel: first.has_panel_data
      });
    } else {
      document.getElementById('demandHeadline').textContent = 'Noch zu wenige Daten (< 20 Signale).';
    }
  } catch (e) {
    document.getElementById('demandHeadline').textContent = `Fehler: ${e.message}`;
  }
}

function renderMarket(d) {
  const pct = Math.round((d.preference_rate || 0) * 100);
  document.getElementById('demandHeadline').textContent =
    `${pct} von 100 Verbrauchern bevorzugten nachhaltigeren Anbau`;
  document.getElementById('prefBar').style.width = `${pct}%`;
  const wtpEl = document.getElementById('wtpValue');
  if (wtpEl) wtpEl.textContent = d.willingness_pct != null ? `+${d.willingness_pct}%` : '–';
}

// ── Opt-in ──────────────────────────────────────────────────────────────────
document.getElementById('btnOptIn').addEventListener('click', () => {
  document.getElementById('optInForm').style.display = 'block';
  document.getElementById('btnOptIn').style.display = 'none';
});
const slider = document.getElementById('wtpSlider');
slider.addEventListener('input', () => {
  document.getElementById('wtpSliderVal').textContent = slider.value + '%';
});
document.getElementById('btnSubmitSignal').addEventListener('click', async () => {
  const body = {
    category: 'food',
    region: 'AT',
    chose_better_field_profile: true,
    willingness_to_pay_pct: parseFloat(slider.value),
    is_panel: false
  };
  try {
    await fetch(`${API_BASE}/demand-signal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  } catch (_) {}
  document.getElementById('optInForm').style.display = 'none';
  document.getElementById('optInThanks').style.display = 'block';
});

// ── Init ────────────────────────────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// Init Lucide icons after DOM is ready
window.addEventListener('load', () => {
  if (window.lucide) lucide.createIcons();
});

loadOverview();
loadMarket();
