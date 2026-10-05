/* PlanetCareScan → PlanetCare Field: Brücke für den SERVER der Verbraucher App (Node 18+).

   Zwei Aufgaben:
   1. getFieldProfile(gtin): Anbauinfo für die Produktseite, 24 h zwischengespeichert.
   2. track(event, { consent }): anonyme Nachfragesignale sammeln und stündlich gebündelt senden.

   Der SERVICE_API_KEY bleibt auf dem Server. Diese Datei NIE im Browser oder in der App ausliefern.

   Beispiel:
     const { PlanetCareFieldBridge } = require("./bridge");
     const bridge = new PlanetCareFieldBridge({
       baseUrl: "https://www.planetcarefield.app",
       apiKey: process.env.PCF_SERVICE_API_KEY
     });
     bridge.startAutoFlush();
*/

"use strict";

const DAY = 24 * 60 * 60 * 1000;
const EVENT_TYPES = new Set(["scan", "compare", "compare_choice", "filter_verified", "survey_wtp"]);
const REGION_RE = /^[A-Z]{2}-[0-9A-Z]{1,3}$/;
const GTIN_RE = /^\d{8,14}$/;

/** ISO 8601 Kalenderwoche, z. B. "2026-W41" */
function isoWeek(d = new Date()) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((t - yearStart) / DAY + 1) / 7);
  return t.getUTCFullYear() + "-W" + String(week).padStart(2, "0");
}

class PlanetCareFieldBridge {
  constructor({ baseUrl, apiKey, fetchImpl, profileTtlMs = DAY, notFoundTtlMs = 6 * 60 * 60 * 1000, maxQueue = 50000, now = () => Date.now() } = {}) {
    if (!baseUrl || !apiKey) throw new Error("baseUrl und apiKey sind Pflicht");
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
    this.fetch = fetchImpl || globalThis.fetch;
    this.profileTtlMs = profileTtlMs;
    this.notFoundTtlMs = notFoundTtlMs;
    this.maxQueue = maxQueue;
    this.now = now;
    this.cache = new Map();   // gtin -> { value, expires }
    this.queue = [];
    this.flushing = null;
    this.timer = null;
  }

  _headers() {
    return { Authorization: "Bearer " + this.apiKey, Accept: "application/json", "Content-Type": "application/json" };
  }

  /** Feldprofil zu einer GTIN oder null (kein Profil oder Dienst nicht erreichbar). Wirft nie. */
  async getFieldProfile(gtin) {
    if (!GTIN_RE.test(String(gtin))) return null;
    const hit = this.cache.get(gtin);
    if (hit && hit.expires > this.now()) return hit.value;
    try {
      const res = await this.fetch(this.baseUrl + "/api/products/" + gtin + "/field-profile", { headers: this._headers() });
      if (res.status === 404) {
        this.cache.set(gtin, { value: null, expires: this.now() + this.notFoundTtlMs });
        return null;
      }
      if (!res.ok) return hit ? hit.value : null;   // bei Störung: alten Wert behalten, nicht cachen
      const value = await res.json();
      this.cache.set(gtin, { value, expires: this.now() + this.profileTtlMs });
      return value;
    } catch (e) {
      return hit ? hit.value : null;
    }
  }

  /**
   * Ereignis vormerken. Ohne Zustimmung passiert NICHTS.
   * event: { type, gtin?, comparedWith?, verified?, comparedVerified?, category, region, panel?, value? }
   * Nutzer ID, IP, Standort usw. werden bewusst nicht übernommen, auch wenn sie mitgegeben werden.
   */
  track(event, { consent } = {}) {
    if (consent !== true) return false;
    if (!event || !EVENT_TYPES.has(event.type)) return false;
    if (!event.category || !REGION_RE.test(event.region || "")) return false;
    const clean = {
      type: event.type,
      category: String(event.category).slice(0, 60),
      region: event.region,
      week: isoWeek(new Date(this.now())),
      panel: event.panel === true
    };
    if (event.gtin && GTIN_RE.test(String(event.gtin))) clean.gtin = String(event.gtin);
    if (typeof event.verified === "boolean") clean.verified = event.verified;
    if (Array.isArray(event.comparedWith)) {
      const pairs = event.comparedWith
        .map((g, i) => [String(g), Array.isArray(event.comparedVerified) ? event.comparedVerified[i] : undefined])
        .filter(([g]) => GTIN_RE.test(g))
        .slice(0, 3);
      clean.comparedWith = pairs.map((p) => p[0]);
      if (pairs.length && pairs.every((p) => typeof p[1] === "boolean")) clean.comparedVerified = pairs.map((p) => p[1]);
    }
    if (event.type === "survey_wtp") {
      const v = Number(event.value);
      if (!(v >= 0 && v <= 100)) return false;
      clean.value = v;
    }
    if (this.queue.length >= this.maxQueue) this.queue.shift();   // älteste verwerfen statt Speicher zu sprengen
    this.queue.push(clean);
    return true;
  }

  /** Warteschlange senden, in Paketen bis 1000. Bei Fehler bleiben die Ereignisse für den nächsten Versuch. */
  async flush() {
    if (this.flushing) return this.flushing;
    this.flushing = (async () => {
      let sent = 0;
      try {
        while (this.queue.length) {
          const chunk = this.queue.slice(0, 1000);
          const res = await this.fetch(this.baseUrl + "/api/demand-events", { method: "POST", headers: this._headers(), body: JSON.stringify({ events: chunk }) });
          if (res.status === 422) {          // ungültige Daten: nicht endlos wiederholen
            this.queue.splice(0, chunk.length);
            continue;
          }
          if (!res.ok) break;
          this.queue.splice(0, chunk.length);
          sent += chunk.length;
        }
      } catch (e) {
        /* Netzfehler: nächster Versuch beim nächsten Intervall */
      } finally {
        this.flushing = null;
      }
      return sent;
    })();
    return this.flushing;
  }

  startAutoFlush(intervalMs = 60 * 60 * 1000) {
    this.stopAutoFlush();
    this.timer = setInterval(() => this.flush(), intervalMs);
    if (this.timer.unref) this.timer.unref();
  }

  stopAutoFlush() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}

module.exports = { PlanetCareFieldBridge, isoWeek };
