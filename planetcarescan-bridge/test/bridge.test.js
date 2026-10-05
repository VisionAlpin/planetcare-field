// Ausführen:  node --test planetcarescan-bridge/test
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const { PlanetCareFieldBridge, isoWeek } = require("../bridge");

function fakeFetch(handler) {
  const calls = [];
  const fn = async (url, opts = {}) => {
    calls.push({ url, opts });
    const r = await handler(url, opts, calls.length);
    return { status: r.status, ok: r.status >= 200 && r.status < 300, json: async () => r.body };
  };
  fn.calls = calls;
  return fn;
}

const base = { baseUrl: "https://pcf.test/", apiKey: "k" };
const ev = { type: "compare_choice", gtin: "9001234567890", comparedWith: ["9009876543210"], verified: true, comparedVerified: [false], category: "Mehl", region: "AT-5" };

test("isoWeek", () => {
  assert.strictEqual(isoWeek(new Date(2026, 9, 6)), "2026-W41");
  assert.strictEqual(isoWeek(new Date(2027, 0, 1)), "2026-W53");
});

test("Feldprofil wird gecacht, 404 ergibt null", async () => {
  let t = 0;
  const f = fakeFetch((url) => (url.includes("9001234567890") ? { status: 200, body: { verified: true, profileScore: 72 } } : { status: 404 }));
  const b = new PlanetCareFieldBridge({ ...base, fetchImpl: f, now: () => t });
  assert.strictEqual((await b.getFieldProfile("9001234567890")).profileScore, 72);
  await b.getFieldProfile("9001234567890");
  assert.strictEqual(f.calls.length, 1);
  assert.strictEqual(f.calls[0].opts.headers.Authorization, "Bearer k");
  assert.strictEqual(await b.getFieldProfile("4000000000000"), null);
  assert.strictEqual(await b.getFieldProfile("abc"), null);
  t += 25 * 60 * 60 * 1000;
  await b.getFieldProfile("9001234567890");
  assert.strictEqual(f.calls.length, 3);
});

test("Störung: alter Wert bleibt, kein Absturz", async () => {
  let t = 0, fail = false;
  const f = fakeFetch(() => { if (fail) throw new Error("down"); return { status: 200, body: { profileScore: 70 } }; });
  const b = new PlanetCareFieldBridge({ ...base, fetchImpl: f, now: () => t });
  await b.getFieldProfile("9001234567890");
  fail = true; t += 2 * 24 * 60 * 60 * 1000;
  assert.strictEqual((await b.getFieldProfile("9001234567890")).profileScore, 70);
});

test("ohne Zustimmung wird nichts gespeichert, Nutzerdaten fallen weg", () => {
  const b = new PlanetCareFieldBridge({ ...base, fetchImpl: fakeFetch(() => ({ status: 202 })), now: () => Date.UTC(2026, 9, 6) });
  assert.strictEqual(b.track(ev, {}), false);
  assert.strictEqual(b.track(ev, { consent: "yes" }), false);
  assert.strictEqual(b.track({ ...ev, userId: "u1", ip: "1.2.3.4", lat: 47.8 }, { consent: true }), true);
  const q = b.queue[0];
  assert.deepStrictEqual(Object.keys(q).sort(), ["category", "comparedVerified", "comparedWith", "gtin", "panel", "region", "type", "verified", "week"]);
  assert.strictEqual(q.week, "2026-W41");
  assert.strictEqual(b.track({ ...ev, region: "Salzburg" }, { consent: true }), false);
  assert.strictEqual(b.track({ type: "survey_wtp", category: "Mehl", region: "AT-5", value: 150 }, { consent: true }), false);
});

test("flush sendet gebündelt und behält Ereignisse bei Fehler", async () => {
  let status = 500;
  const f = fakeFetch(() => ({ status }));
  const b = new PlanetCareFieldBridge({ ...base, fetchImpl: f });
  for (let i = 0; i < 1500; i++) b.track(ev, { consent: true });
  assert.strictEqual(await b.flush(), 0);
  assert.strictEqual(b.queue.length, 1500);
  status = 202;
  assert.strictEqual(await b.flush(), 1500);
  assert.strictEqual(b.queue.length, 0);
  assert.strictEqual(f.calls.length, 3);
  assert.strictEqual(JSON.parse(f.calls[1].opts.body).events.length, 1000);
});
