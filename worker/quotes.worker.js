/**
 * quotes.worker.js — a tiny Cloudflare Worker that serves live (~real-time to
 * 15-min delayed) last-prices to the otherwise-static GitHub Pages dashboard.
 *
 * WHY a worker: GitHub Pages can't push or hold a secret. This edge endpoint
 * (a) keeps the Polygon key server-side (env.POLYGON_API_KEY, sent as an
 * Authorization header — never in a cached URL), (b) routes US symbols -> Polygon
 * snapshot and everything else -> Yahoo spark (keyless), and (c) edge-caches each
 * response under a CANONICAL (sorted, de-duped) symbol key so a fan of browsers
 * polling the same set costs one upstream call and can't fragment/poison the cache
 * by reordering. It mirrors the Python engine.live_quotes routing + price_basis so
 * the bot feed and the website agree to the last digit.
 *
 * Contract:
 *   GET /quotes?symbols=AAPL,0700.HK,GC=F
 *     -> { "ts": <ms>, "quotes": { "AAPL": {price, ts, source, basis, prevClose}, ... } }
 *   GET /health -> { ok: true }
 *
 * Deploy: `wrangler deploy`; set the key with `wrangler secret put POLYGON_API_KEY`.
 * Then put the deployed URL into config.yml live.quotes_worker_url.
 */

const CACHE_SEC = 60;            // edge-cache window; matches live.poll_seconds
const MAX_SYMBOLS = 200;
// Yahoo's spark endpoint HTTP-400s a symbols list longer than ~20 (20 OK, 21
// fails). Sending a whole 100+ symbol board in one call silently lost EVERY intl
// quote. Chunk under the cliff and run the chunks concurrently.
const YAHOO_BATCH = 20;
const SYMBOL_RE = /^[A-Z0-9^][A-Z0-9.=^-]{0,15}$/;   // ticker charset (^VIX, GC=F, 0700.HK, BRK-B)
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(obj, extra) {
  return new Response(JSON.stringify(obj), {
    headers: { "Content-Type": "application/json", ...CORS, ...(extra || {}) },
  });
}

const round4 = (x) => Math.round(x * 1e4) / 1e4;

// US equity/ETF (Polygon-routable) — no suffix / future / crypto / caret marker.
function isUS(sym) {
  return sym && !/[.=^-]/.test(sym);
}

async function fetchPolygon(symbols, env, out) {
  const key = env && env.POLYGON_API_KEY;
  if (!key) return symbols;                       // no key -> all fall through to Yahoo
  const base = (env.POLYGON_BASE_URL || "https://api.polygon.io").replace(/\/$/, "");
  // key in a header, not the URL: keeps it out of the CF subrequest cache + logs.
  const url = `${base}/v2/snapshot/locale/us/markets/stocks/tickers` +
              `?tickers=${encodeURIComponent(symbols.join(","))}`;
  try {
    const r = await fetch(url, { headers: { Authorization: `Bearer ${key}` }, cf: { cacheTtl: CACHE_SEC } });
    if (!r.ok) return symbols;
    const j = await r.json();
    const got = new Set();
    for (const t of (j.tickers || [])) {
      const lt = t.lastTrade || {}, mn = t.min || {}, day = t.day || {}, prev = t.prevDay || {};
      let price, basis, ts;
      if (lt.p) { price = lt.p; basis = "trade"; ts = lt.t ? Math.round(lt.t / 1e6) : null; }
      else if (mn.c) { price = mn.c; basis = "minute"; ts = mn.t ? Math.round(mn.t) : null; }
      else if (day.c) { price = day.c; basis = "day"; }
      else if (prev.c) { price = prev.c; basis = "prev"; }
      if (!price) continue;
      if (ts == null) ts = t.updated ? Math.round(t.updated / 1e6) : Date.now();
      out[t.ticker] = {
        price: round4(price), ts, source: "polygon", basis,
        prevClose: prev.c != null ? round4(prev.c) : null,
      };
      got.add(t.ticker);
    }
    return symbols.filter((s) => !got.has(s));    // leftovers -> Yahoo fallback
  } catch (e) {
    return symbols;
  }
}

async function fetchYahooChunk(symbols, out) {
  const url = "https://query1.finance.yahoo.com/v7/finance/spark" +
              `?symbols=${encodeURIComponent(symbols.join(","))}&range=1d&interval=5m`;
  try {
    const r = await fetch(url, { cf: { cacheTtl: CACHE_SEC } });
    if (!r.ok) return;
    const j = await r.json();
    for (const res of ((j.spark && j.spark.result) || [])) {
      const meta = ((res.response || [{}])[0] || {}).meta || {};
      if (meta.regularMarketPrice == null) continue;
      out[res.symbol] = {
        price: round4(meta.regularMarketPrice),
        ts: meta.regularMarketTime ? meta.regularMarketTime * 1000 : Date.now(),
        source: "yahoo", basis: "regular",
        prevClose: meta.previousClose != null ? round4(meta.previousClose) : null,
      };
    }
  } catch (e) { /* degrade: symbol simply absent */ }
}

async function fetchYahoo(symbols, out) {
  if (!symbols.length) return;
  const chunks = [];
  for (let i = 0; i < symbols.length; i += YAHOO_BATCH) chunks.push(symbols.slice(i, i + YAHOO_BATCH));
  await Promise.all(chunks.map((c) => fetchYahooChunk(c, out)));
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    const url = new URL(request.url);
    if (url.pathname === "/health") return json({ ok: true });
    if (url.pathname !== "/quotes") return new Response("not found", { status: 404, headers: CORS });

    // canonical symbol set: upper, charset-validated, de-duped, sorted, capped.
    const symbols = [...new Set((url.searchParams.get("symbols") || "")
      .split(",").map((s) => s.trim().toUpperCase()).filter((s) => SYMBOL_RE.test(s)))]
      .sort().slice(0, MAX_SYMBOLS);
    if (!symbols.length) return json({ ts: Date.now(), quotes: {} });

    // cache key derived ONLY from the canonical set, so order/whitespace/dupes
    // and extraneous query params can't fragment or poison the edge cache.
    const cache = caches.default;
    const cacheKey = new Request("https://quotes.cache/quotes?symbols=" +
      encodeURIComponent(symbols.join(",")), { method: "GET" });
    const hit = await cache.match(cacheKey);
    if (hit) return hit;

    const quotes = {};
    const leftover = await fetchPolygon(symbols.filter(isUS), env, quotes);
    await fetchYahoo([...symbols.filter((s) => !isUS(s)), ...leftover], quotes);

    const resp = json({ ts: Date.now(), quotes },
                      { "Cache-Control": `public, max-age=${CACHE_SEC}` });
    ctx.waitUntil(cache.put(cacheKey, resp.clone()));
    return resp;
  },
};
