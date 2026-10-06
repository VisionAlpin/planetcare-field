/* PlanetCare Field: Tab "Markt". Zeigt je Produktkategorie, wie oft Verbraucher in der Region
   das Produkt mit verifiziertem Anbau wählen, und die Zahlungsbereitschaft. Quelle: /api/market-signal */

(function () {
  "use strict";

  const MIN = 20;
  const SAMPLE = [
    { category: "Mehl", region: "AT-5", events: 412, preferenceRate: 0.68, comparisons: 96, willingnessToPayMedian: 10, surveyAnswers: 58, panelShare: 0.7, weeks: 12 },
    { category: "Brot", region: "AT-5", events: 233, preferenceRate: 0.61, comparisons: 41, willingnessToPayMedian: 5, surveyAnswers: 33, panelShare: 0.8, weeks: 12 },
    { category: "Nudeln", region: "AT-5", events: 88, preferenceRate: null, comparisons: 12, willingnessToPayMedian: null, surveyAnswers: 9, panelShare: 0.9, weeks: 12 }
  ];
  const REGIONS = { "AT-1": "Burgenland", "AT-2": "Kärnten", "AT-3": "Niederösterreich", "AT-4": "Oberösterreich", "AT-5": "Salzburg", "AT-6": "Steiermark", "AT-7": "Tirol", "AT-8": "Vorarlberg", "AT-9": "Wien", "DE-BY": "Bayern", "DE-BW": "Baden-Württemberg" };

  const root = document.querySelector("[data-market]");
  const meta = document.querySelector("[data-market-meta]");
  if (!root) return;
  let loadedFor = null;

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  const pct = (v) => Math.round(v * 100);

  function card(s) {
    const pref = s.preferenceRate == null
      ? '<p class="mk-empty">Noch zu wenige Vergleiche für eine Aussage (' + s.comparisons + " von " + MIN + ").</p>"
      : '<div class="mk-bar" role="img" aria-label="' + pct(s.preferenceRate) + ' Prozent wählen das Produkt mit verifiziertem Anbau">' +
          '<span class="mk-fill" style="width:' + pct(s.preferenceRate) + '%"></span><span class="mk-mid" title="Gleichstand"></span></div>' +
        '<p class="mk-value"><strong class="num">' + pct(s.preferenceRate) + " %</strong> wählen das Produkt mit verifiziertem Anbau " +
        '<span class="mk-n num">(' + s.comparisons + " Vergleiche)</span></p>";
    const wtp = s.willingnessToPayMedian == null
      ? '<p class="mk-empty">Zahlungsbereitschaft: noch zu wenige Antworten (' + s.surveyAnswers + " von " + MIN + ").</p>"
      : '<p class="mk-value">Zahlungsbereitschaft: <strong class="num">+' + String(s.willingnessToPayMedian).replace(".", ",") + " %</strong> Aufpreis " +
        '<span class="mk-n num">(Median aus ' + s.surveyAnswers + " Antworten)</span></p>";
    return (
      '<article class="mk-card">' +
      '<div class="mk-head"><h2>' + esc(s.category) + '</h2><span class="mk-n num">' + s.events + " Signale" +
      (s.panelShare > 0 ? " · " + pct(s.panelShare) + " % aus dem Pilotpanel" : "") + "</span></div>" +
      pref + wtp +
      "</article>"
    );
  }

  function render(list, sample) {
    const items = list.slice().sort((a, b) => b.events - a.events);
    root.innerHTML =
      (sample ? '<p class="mk-note">Beispieldaten zur Ansicht. Echte Werte erscheinen, sobald die Verbraucher App Signale liefert.</p>' : "") +
      (items.length
        ? '<div class="mk-grid">' + items.map(card).join("") + "</div>"
        : '<div class="mk-note">In dieser Region liegen noch keine Nachfragesignale vor. Sie entstehen, wenn Nutzer der Verbraucher App zustimmen, ihre Kaufentscheidungen anonym zu teilen.</div>') +
      '<p class="mk-foot">Präferenz: Anteil der Vergleiche, in denen Verbraucher das Produkt mit verifiziertem Anbau gewählt haben, wenn sich die Produkte darin unterschieden. 50 % entspricht Gleichstand. ' +
      "Werte erscheinen ab " + MIN + " Vergleichen bzw. Antworten, damit niemand identifizierbar ist. Zeitraum: letzte 12 Wochen.</p>";
  }

  async function load(region) {
    if (loadedFor === region) return;
    loadedFor = region;
    meta.textContent = "Was Verbraucher in " + (REGIONS[region] || region) + " beim Einkauf wählen";
    const pcf = window.PlanetCareField;
    if (pcf.mode() === "offline") return render(SAMPLE, true);
    root.innerHTML = '<p class="mk-note">Wird geladen …</p>';
    try {
      const res = await fetch("/api/market-signal?region=" + encodeURIComponent(region), { credentials: "same-origin", headers: pcf.apiHeaders() });
      if (res.status === 401) { location.href = "/login"; return; }
      if (!res.ok) throw new Error("Fehler " + res.status);
      render(await res.json(), false);
    } catch (e) {
      loadedFor = null;
      root.innerHTML = '<p class="mk-note is-error">Das Marktsignal konnte nicht geladen werden. ' + esc(e.message) + "</p>";
    }
  }

  window.PCFMarket = { load: () => load((window.PCF_CURRENT && window.PCF_CURRENT.regionCode) || "AT-5") };
})();
