/* Heavy-store data base — route the per-ticker OHLC + search-library fetches to a
   CDN / object store (Cloudflare R2) when window.DATA_BASE is set. When it is EMPTY
   (the default) this is a strict NO-OP: the relative-path fetches resolve from
   GitHub Pages exactly as before, so shipping this changes nothing until we
   deliberately flip DATA_BASE at deploy. One shim replaces per-page fetch edits and
   can never miss a call site. Injected in <head> (non-deferred) by
   scripts/inject_data_base.py so it patches window.fetch BEFORE any page data fetch.

   THE FLIP (later): set DATA_BASE below to the R2 public URL (or a custom domain),
   enable the bucket's public access + CORS, redeploy. Everything then loads from R2. */
(function () {
  window.DATA_BASE = window.DATA_BASE || "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev";  // R2 public data plane (flip: clear to revert to Pages)
  var B = window.DATA_BASE;
  if (!B) return;                                         // no-op when unset -> zero behavior change
  B = B.replace(/\/+$/, "");                              // strip trailing slash
  // the per-ticker stores that live in R2 (mirror scripts/publish_r2.py DEFAULT_DIRS)
  var RE = /^(ohlc|chinaohlc|hkohlc|intlohlc|canadaohlc|subsectorohlc(?:_china|_russell|_nasdaq)?|stockdata|chinastockdata|hkstockdata|canadastockdata|intlstockdata|intraday)\//;
  var orig = window.fetch;
  window.fetch = function (u, o) {
    try {
      if (typeof u === "string") {
        /* theme.js resolves shared assets from its own script URL, so its stock
           libraries arrive here as absolute same-origin URLs.  The old shim only
           recognized bare/../ paths, leaving those requests on the protected HTML
           origin (401 on Start) and the search spinner alive forever.  Normalize
           every same-origin string to a root-relative key before matching; preserve
           query/hash cache keys, and never rewrite an already-external URL. */
        var a = new URL(u, location.href);
        if (a.origin === location.origin) {
          var rel = a.pathname.replace(/^\/+/, "") + a.search + a.hash;
          if (RE.test(rel)) u = B + "/" + rel;            // -> https://<data-host>/ohlc/AAPL.json
        }
      }
    } catch (e) { /* never let the shim break a fetch */ }
    return orig.call(this, u, o);
  };
})();
