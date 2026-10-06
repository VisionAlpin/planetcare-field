/* PlanetCare Field: Rahmen der App. Tabs per Adresse (#uebersicht, #felder, #markt),
   Demo Kennzeichnung, angemeldeter Nutzer und Abmelden. */

(function () {
  "use strict";
  const pcf = window.PlanetCareField;
  const m = pcf.mode();

  // Demo Kennzeichnung nur in Demo und offline
  document.querySelector("[data-demo-badge]").hidden = m === "app";
  if (m === "demo") document.querySelector("[data-login-link]").hidden = false;

  // Angemeldeter Nutzer
  if (m === "app") {
    fetch("/api/auth/me", { credentials: "same-origin", headers: pcf.apiHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then((me) => {
        if (!me) return;
        const el = document.querySelector("[data-user-email]");
        el.textContent = me.email || "";
        el.hidden = !me.email;
        document.querySelector("[data-logout]").hidden = false;
      })
      .catch(() => {});
    document.querySelector("[data-logout]").addEventListener("click", async () => {
      try { await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }); } catch (e) { /* trotzdem weiter */ }
      location.href = "/login?abgemeldet=1";
    });
  }

  // Tabs
  const VIEWS = ["uebersicht", "felder", "markt"];
  function show() {
    const v = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "uebersicht";
    document.querySelectorAll("[data-view]").forEach((el) => { el.hidden = el.dataset.view !== v; });
    document.querySelectorAll(".tab").forEach((t) => {
      if (t.getAttribute("href") === "#" + v) t.setAttribute("aria-current", "page");
      else t.removeAttribute("aria-current");
    });
    if (v === "markt" && window.PCFMarket) {
      if (window.PCF_CURRENT) window.PCFMarket.load();
      else document.addEventListener("pcf:overview", () => window.PCFMarket.load(), { once: true });
    }
  }
  window.addEventListener("hashchange", show);
  show();
})();
