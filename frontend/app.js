/* PlanetCare Field — Frontend App */

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : 'https://field.planetcarescan.app';

const params = new URLSearchParams(location.search);
const DEMO = params.get('demo') === '1';
const FIELD_ID = params.get('field') || null;

// ── Demo Mock Data ──────────────────────────────────────────────────────────
const DEMO_DATA = {
  farm: { name: "Musterbetrieb Oberösterreich", region: "AT-4" },
  field: { name: "Schlag Süd", area_ha: 12.4, crop_type: "Winterweizen" },
  profile: {
    score_total: 71, score_water: 78, score_biodiversity: 65, score_pesticide: null,
    method_version: "1.0", calculated_at: "2026-09-28"
  },
  satellite: {
    ndvi_mean: 0.62, ndvi_std: 0.11, cloud_cover: 8, date: "2026-09-28",
    scene_id: "S2B_32TPT_20260928"
  },
  demand: { preference_rate: 0.68, willingness_pct: 12, n_events: 47, trend: "+3%", has_panel: false }
};

// Demo field geometry (Austria, near Linz)
const DEMO_GEOMETRY = {
  type: "Polygon",
  coordinates: [[[14.28, 48.30], [14.31, 48.30], [14.31, 48.32], [14.28, 48.32], [14.28, 48.30]]]
};

// ── Info Texts ──────────────────────────────────────────────────────────────
const INFO = {
  water: {
    title: "Wasser-Score",
    text: "Berechnet aus NDVI-Mittelwert (Vegetationsgesundheit) und dem Combined Drought Indicator (CDI) des Copernicus Emergency Management Service. Datenquelle: Sentinel-2 (ESA), CDI (EU Copernicus)."
  },
  bio: {
    title: "Biodiversitäts-Score",
    text: "Abgeleitet aus der räumlichen Variabilität des NDVI (Standardabweichung). Höhere Heterogenität der Vegetation korreliert mit höherer Biodiversität. Datenquelle: Sentinel-2 L2A."
  },
  pest: {
    title: "Pflanzenschutz-Score",
    text: "Basiert auf manuell eingegebenen Angaben zum Pestizideinsatz (kg Wirkstoff/ha). In Phase 0 optional — ein fehlender Wert bedeutet keine Aussage, nicht kein Einsatz."
  }
};

// ── Tab Navigation ──────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    if (btn.dataset.tab === 'map' && !window._mapInit) initMap();
  });
});

// ── Info Modal ──────────────────────────────────────────────────────────────
document.querySelectorAll('.info-btn').forEach(btn => {
  btn.addEventListener('click', () => {
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

// ── Score Ring ──────────────────────────────────────────────────────────────
function setScore(total) {
  const el = document.getElementById('ringFill');
  const num = document.getElementById('scoreTotal');
  if (total == null) { num.textContent = '–'; return; }
  const circ = 2 * Math.PI * 50; // r=50
  const offset = circ - (total / 100) * circ;
  el.style.strokeDasharray  = circ;
  el.style.strokeDashoffset = offset;
  el.style.stroke = total >= 70 ? 'var(--good)' : total >= 40 ? 'var(--yellow)' : 'var(--red)';
  num.textContent = total;
}

function setIndicator(scoreEl, metaEl, cardEl, value, source, date) {
  if (value == null) {
    scoreEl.textContent = 'Nicht verfügbar';
    scoreEl.style.fontSize = '1rem';
    metaEl.textContent = '';
    cardEl.className = 'indicator-card';
  } else {
    scoreEl.textContent = value;
    scoreEl.style.fontSize = '';
    metaEl.textContent = [source, date ? formatDate(date) : ''].filter(Boolean).join(' · ');
    const cls = value >= 70 ? 'good' : value >= 40 ? 'mid' : 'bad';
    cardEl.className = `indicator-card ${cls}`;
  }
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// ── Load Overview Data ──────────────────────────────────────────────────────
async function loadOverview() {
  if (DEMO) {
    document.getElementById('demoBadge').style.display = '';
    renderOverview(DEMO_DATA);
    return;
  }
  if (!FIELD_ID) {
    document.getElementById('farmTitle').textContent = 'Kein Schlag-Parameter (?field=ID) angegeben';
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
      farm: { name: data.field_id },
      profile: data.profile,
    });
  } catch (e) {
    document.getElementById('farmTitle').textContent = `Fehler: ${e.message}`;
  }
}

function renderOverview(data) {
  const { farm, field, profile } = data;
  document.getElementById('farmTitle').textContent =
    `${farm?.name || ''}${field?.name ? ' · ' + field.name : ''}`;

  setScore(profile?.score_total ?? null);
  setIndicator(
    document.getElementById('scoreWater'),
    document.getElementById('metaWater'),
    document.getElementById('cardWater'),
    profile?.score_water ?? null,
    'Sentinel-2 + CDI',
    profile?.calculated_at
  );
  setIndicator(
    document.getElementById('scoreBio'),
    document.getElementById('metaBio'),
    document.getElementById('cardBio'),
    profile?.score_biodiversity ?? null,
    'Sentinel-2',
    profile?.calculated_at
  );
  setIndicator(
    document.getElementById('scorePest'),
    document.getElementById('metaPest'),
    document.getElementById('cardPest'),
    profile?.score_pesticide ?? null,
    'Manuelle Eingabe',
    profile?.calculated_at
  );
  document.getElementById('methodVersion').textContent = profile?.method_version || '1.0';
  document.getElementById('calcDate').textContent = profile?.calculated_at ? formatDate(profile.calculated_at) : '–';
}

// ── Map ─────────────────────────────────────────────────────────────────────
let map;
window._mapInit = false;

function initMap() {
  window._mapInit = true;
  map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8,
      sources: {
        osm: {
          type: 'raster',
          tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          attribution: '© OpenStreetMap contributors'
        }
      },
      layers: [{ id: 'osm', type: 'raster', source: 'osm' }]
    },
    center: [14.3, 48.3],
    zoom: 12
  });

  map.on('load', () => {
    const geom = DEMO ? DEMO_GEOMETRY : null;
    if (geom) showFieldOnMap(geom);
  });

  // Field info
  if (DEMO) {
    const f = DEMO_DATA.field;
    document.getElementById('fieldName').textContent = f.name;
    document.getElementById('fieldArea').textContent = `${f.area_ha} ha`;
    document.getElementById('fieldCrop').textContent = f.crop_type;
  }
}

function showFieldOnMap(geometry) {
  if (!map) return;
  const geojson = { type: 'Feature', geometry, properties: {} };
  if (map.getSource('field')) {
    map.getSource('field').setData(geojson);
  } else {
    map.addSource('field', { type: 'geojson', data: geojson });
    map.addLayer({
      id: 'field-fill',
      type: 'fill',
      source: 'field',
      paint: { 'fill-color': '#e8b86d', 'fill-opacity': 0.3 }
    });
    map.addLayer({
      id: 'field-outline',
      type: 'line',
      source: 'field',
      paint: { 'line-color': '#e8b86d', 'line-width': 2 }
    });
  }
  // Fit bounds
  const coords = geometry.coordinates[0];
  const lons = coords.map(c => c[0]);
  const lats = coords.map(c => c[1]);
  map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 40 });
}

document.getElementById('btnDrawField').addEventListener('click', () => {
  const panel = document.getElementById('geojsonInput');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
});

document.getElementById('btnApplyGeojson').addEventListener('click', () => {
  try {
    const raw = document.getElementById('geojsonTextarea').value.trim();
    const geom = JSON.parse(raw);
    showFieldOnMap(geom);
    document.getElementById('geojsonInput').style.display = 'none';
  } catch (e) {
    alert('Ungültiges GeoJSON: ' + e.message);
  }
});

document.getElementById('btnLoadSatellite').addEventListener('click', async () => {
  if (DEMO) {
    const s = DEMO_DATA.satellite;
    document.getElementById('satelliteStatus').style.display = 'block';
    document.getElementById('satelliteStatus').innerHTML =
      `✓ Sentinel-2 Daten: NDVI ${s.ndvi_mean} (±${s.ndvi_std}) · Wolken ${s.cloud_cover}% · ${s.date}<br><small>${s.scene_id}</small>`;
    return;
  }
  if (!FIELD_ID) { alert('Kein Schlag-Parameter gesetzt (?field=ID)'); return; }
  const token = localStorage.getItem('pcf_token') || '';
  const status = document.getElementById('satelliteStatus');
  status.style.display = 'block';
  status.textContent = '⏳ Satellitendaten werden abgerufen…';
  try {
    const r = await fetch(`${API_BASE}/fields/${FIELD_ID}/fetch-satellite`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    });
    const job = await r.json();
    status.textContent = `Job gestartet: ${job.job_id} — Status: ${job.status}`;
    pollJob(job.job_id, FIELD_ID);
  } catch (e) {
    status.textContent = `Fehler: ${e.message}`;
  }
});

async function pollJob(jobId, fieldId) {
  const status = document.getElementById('satelliteStatus');
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 3000));
    try {
      const r = await fetch(`${API_BASE}/fields/${fieldId}/satellite-status/${jobId}`);
      const job = await r.json();
      if (job.status === 'done') {
        const n = job.ndvi || {};
        status.textContent = `✓ NDVI: ${n.ndvi_mean} (±${n.ndvi_std}) · Wolken: ${n.cloud_cover}% · ${n.date}`;
        return;
      } else if (job.status === 'error') {
        status.textContent = `Fehler: ${job.error}`;
        return;
      }
      status.textContent = `⏳ ${job.status}…`;
    } catch (e) { /* retry */ }
  }
  status.textContent = 'Timeout — bitte später neu laden.';
}

// ── Market Signals ──────────────────────────────────────────────────────────
async function loadMarket() {
  if (DEMO) {
    renderMarket(DEMO_DATA.demand);
    return;
  }
  try {
    const r = await fetch(`${API_BASE}/demand-signal/summary`);
    const data = await r.json();
    const first = data.summary?.[0];
    if (first) {
      renderMarket({
        preference_rate: first.preference_rate,
        willingness_pct: first.willingness_to_pay_pct_median,
        n_events: first.n_events,
        has_panel: first.has_panel_data
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
  document.getElementById('wtpValue').textContent =
    d.willingness_pct != null ? `+${d.willingness_pct}%` : '–';
  if (d.has_panel) document.getElementById('panelNote').style.display = 'block';
}

// ── Opt-in Form ─────────────────────────────────────────────────────────────
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
  } catch (e) { /* best effort */ }
  document.getElementById('optInForm').style.display = 'none';
  document.getElementById('optInThanks').style.display = 'block';
});

// ── Init ────────────────────────────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

loadOverview();
loadMarket();
