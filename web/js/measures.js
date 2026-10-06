/* PlanetCare Field: Behandlungen (Pflanzenschutz) eintragen und anzeigen.
   Öffnet sich über Links mit data-open-measures. Nutzt window.PCF_CURRENT aus overview.js.
   In der Demo (/demo) und offline nur lesend. */

(function () {
  "use strict";

  const KIND_LABELS = { fungizid: "Fungizid", herbizid: "Herbizid", insektizid: "Insektizid", wachstumsregler: "Wachstumsregler" };
  const DEMO_LIST = [
    { id: "d1", day: "2026-05-20", kind: "fungizid", kindLabel: "Fungizid", product: null, amount: null, unit: null },
    { id: "d2", day: "2026-04-28", kind: "herbizid", kindLabel: "Herbizid", product: null, amount: null, unit: null }
  ];

  const dlg = document.getElementById("measures-dialog");
  if (!dlg) return;
  const form = dlg.querySelector("form");
  const list = dlg.querySelector("[data-measures-list]");
  const msg = dlg.querySelector("[data-measures-msg]");
  const title = dlg.querySelector("[data-measures-title]");

  const offline = window.PlanetCareField.mode() === "offline";
  const readOnly = window.PlanetCareField.mode() !== "app";

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function fmtDate(iso) {
    const [y, m, d] = iso.split("-");
    return d + "." + m + "." + y;
  }
  function say(text, isError) {
    msg.textContent = text || "";
    msg.classList.toggle("is-error", !!isError);
  }

  async function api(path, opts) {
    const res = await fetch(path, Object.assign({ credentials: "same-origin", headers: window.PlanetCareField.apiHeaders({ "Content-Type": "application/json" }) }, opts));
    if (res.status === 401) { location.href = "/login"; throw new Error("401"); }
    if (!res.ok && res.status !== 204) {
      let detail = "Fehler " + res.status;
      try { const b = await res.json(); detail = typeof b.detail === "string" ? b.detail : detail; } catch (e) { /* leer */ }
      throw new Error(detail);
    }
    return res.status === 204 ? null : res.json();
  }

  function render(items) {
    if (!items.length) {
      list.innerHTML = '<p class="measures-empty">In dieser Saison sind noch keine Behandlungen eingetragen.</p>';
      return;
    }
    list.innerHTML =
      '<ul class="measures-list">' +
      items.map((m) =>
        '<li><div><strong class="num">' + fmtDate(m.day) + "</strong> · " + esc(m.kindLabel || KIND_LABELS[m.kind]) +
        (m.product ? " · " + esc(m.product) : "") +
        (m.amount != null ? ' · <span class="num">' + esc(String(m.amount).replace(".", ",")) + " " + esc(m.unit) + "</span>" : "") +
        "</div>" +
        (readOnly ? "" : '<button type="button" class="link-danger" data-delete="' + esc(m.id) + '" aria-label="Eintrag vom ' + fmtDate(m.day) + ' löschen">Löschen</button>') +
        "</li>"
      ).join("") +
      "</ul>";
  }

  async function load() {
    const cur = window.PCF_CURRENT || {};
    title.textContent = "Behandlungen · " + (cur.fieldName || "") + " · " + (cur.season || "");
    if (offline) return render(DEMO_LIST);
    list.innerHTML = '<p class="measures-empty">Wird geladen …</p>';
    try {
      render(await api("/api/fields/" + encodeURIComponent(cur.fieldId) + "/measures?season=" + cur.season));
    } catch (e) {
      list.innerHTML = "";
      say("Die Einträge konnten nicht geladen werden. " + e.message, true);
    }
  }

  function open() {
    say("");
    form.hidden = readOnly;
    dlg.querySelector("[data-readonly-note]").hidden = !readOnly;
    if (!readOnly) {
      form.reset();
      form.day.value = new Date().toISOString().slice(0, 10);
      form.day.max = form.day.value;
    }
    dlg.showModal();
    load();
  }

  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-open-measures]");
    if (a) { e.preventDefault(); open(); }
  });
  dlg.querySelector("[data-close]").addEventListener("click", () => dlg.close());

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const cur = window.PCF_CURRENT || {};
    const amount = form.amount.value.trim();
    const body = {
      day: form.day.value,
      kind: form.kind.value,
      product: form.product.value.trim() || null,
      amount: amount ? Number(amount.replace(",", ".")) : null,
      unit: amount ? form.unit.value : null
    };
    if (!body.day || !body.kind) return say("Bitte Datum und Art angeben.", true);
    if (amount && !(body.amount >= 0)) return say("Menge bitte als Zahl angeben.", true);
    const btn = form.querySelector("[type=submit]");
    btn.disabled = true;
    try {
      await api("/api/fields/" + encodeURIComponent(cur.fieldId) + "/measures", { method: "POST", body: JSON.stringify(body) });
      say("Gespeichert. Wird bei der nächsten Berechnung in der Nacht berücksichtigt.");
      form.product.value = "";
      form.amount.value = "";
      load();
    } catch (err) {
      say("Speichern fehlgeschlagen: " + err.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  list.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-delete]");
    if (!b) return;
    if (!window.confirm("Diesen Eintrag löschen?")) return;
    try {
      await api("/api/measures/" + encodeURIComponent(b.dataset.delete), { method: "DELETE" });
      say("Gelöscht.");
      load();
    } catch (err) {
      say("Löschen fehlgeschlagen: " + err.message, true);
    }
  });
})();
