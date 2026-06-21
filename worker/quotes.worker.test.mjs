// Offline test of quotes.worker.js — proves the routing / canonicalization / contract
// without deploying. Mocks fetch (Polygon snapshot + Yahoo spark), caches, and ctx.
// Run: node quotes.worker.test.mjs   (node 18+; uses global Request/Response/URL).
import assert from "node:assert/strict";
import worker from "./quotes.worker.js";

let polygonHits = 0, yahooHits = 0;
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes("polygon.io")) {
    polygonHits++;
    assert.ok(u.includes("tickers=AAPL"), "polygon should get only the US symbol");
    return new Response(JSON.stringify({
      tickers: [{ ticker: "AAPL", lastTrade: { p: 212.5, t: 1.7e18 }, prevDay: { c: 210.0 } }],
    }), { status: 200 });
  }
  if (u.includes("finance.yahoo.com")) {
    yahooHits++;
    // both non-US symbols routed here (0700.HK, GC=F)
    assert.ok(u.includes("0700.HK") && u.includes("GC%3DF") || u.includes("GC=F"),
      "yahoo should get the non-US symbols");
    return new Response(JSON.stringify({
      spark: { result: [
        { symbol: "0700.HK", response: [{ meta: { regularMarketPrice: 350.2, previousClose: 348.0, regularMarketTime: 1.7e9 } }] },
        { symbol: "GC=F", response: [{ meta: { regularMarketPrice: 2350.5, previousClose: 2340.0 } }] },
      ] },
    }), { status: 200 });
  }
  throw new Error("unexpected fetch: " + u);
};
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
const ctx = { waitUntil: () => {} };
const env = { POLYGON_API_KEY: "test-key" };

function req(qs) { return new Request("https://w.dev/quotes?symbols=" + qs); }

let passed = 0;
async function test(name, fn) { await fn(); passed++; console.log("  ✓ " + name); }

console.log("quotes.worker.js:");

await test("routes US→Polygon, non-US→Yahoo; correct contract", async () => {
  // lowercase + duplicate + unsorted input exercises canonicalization too
  const r = await worker.fetch(req("aapl,0700.hk,gc=f,aapl"), env, ctx);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Access-Control-Allow-Origin"), "*", "CORS header");
  const b = await r.json();
  assert.ok(typeof b.ts === "number" && b.quotes, "shape {ts, quotes}");
  assert.equal(b.quotes.AAPL.source, "polygon");
  assert.equal(b.quotes.AAPL.basis, "trade");
  assert.equal(b.quotes.AAPL.price, 212.5);
  assert.equal(b.quotes.AAPL.prevClose, 210.0);
  assert.equal(b.quotes["0700.HK"].source, "yahoo");
  assert.equal(b.quotes["GC=F"].source, "yahoo");
  assert.equal(b.quotes["GC=F"].price, 2350.5);
  assert.equal(polygonHits, 1, "one polygon call for the fan");
  assert.equal(yahooHits, 1, "one yahoo call for the fan");
});

await test("no POLYGON_API_KEY → US symbol falls back to Yahoo", async () => {
  // with no key, fetchPolygon returns all symbols → everything goes to Yahoo.
  globalThis.fetch = async (url) => {
    const u = String(url);
    assert.ok(u.includes("finance.yahoo.com"), "no-key path must not call polygon");
    return new Response(JSON.stringify({
      spark: { result: [{ symbol: "AAPL", response: [{ meta: { regularMarketPrice: 211.1, previousClose: 210 } }] }] },
    }), { status: 200 });
  };
  const r = await worker.fetch(req("AAPL"), {}, ctx);
  const b = await r.json();
  assert.equal(b.quotes.AAPL.source, "yahoo");
});

await test("rejects junk symbols / empty set; /health ok", async () => {
  const r = await worker.fetch(req("'';DROP,<script>"), env, ctx);
  const b = await r.json();
  assert.deepEqual(b.quotes, {}, "junk symbols filtered to empty");
  const h = await worker.fetch(new Request("https://w.dev/health"), env, ctx);
  assert.equal((await h.json()).ok, true);
});

console.log(`\n${passed} passed`);
