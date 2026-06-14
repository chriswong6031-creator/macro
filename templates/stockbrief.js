/* Single-stock AI brief panel — fetches site/stockbrief/<safe>.json (precomputed
   by engine/catalyst_stock.py). RESEARCH CONTEXT ONLY — never a signal. The panel
   stays hidden unless a usable brief loads (so it's invisible when the feature is
   off or the ticker wasn't precomputed). All model output is escaped before
   insertion — no raw HTML is ever trusted from the JSON. Exposes
   window.loadStockBrief(safe), called by stock.html's load(). */
(function () {
  function esc(s) { var d = document.createElement("div"); d.textContent = (s == null ? "" : String(s)); return d.innerHTML; }
  function list(a) { return '<ul class="sb-list">' + a.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>"; }
  function sec(title, body) { return '<div class="sb-sec"><div class="sb-h">' + esc(title) + "</div>" + body + "</div>"; }
  function usable(b) {
    return b && (b.summary || (b.drivers && b.drivers.length) ||
                 (b.risks && b.risks.length) || (b.catalysts && b.catalysts.length));
  }

  function render(b) {
    var panel = document.getElementById("stock-brief");
    var body = document.getElementById("stock-brief-body");
    if (!panel || !body) return;
    if (!usable(b)) { panel.style.display = "none"; return; }   // degraded/empty -> stay hidden
    var h = "";
    if (b.summary) h += '<p class="sb-sum">' + esc(b.summary) + "</p>";
    if (b.drivers && b.drivers.length) h += sec("Drivers", list(b.drivers));
    if (b.risks && b.risks.length) h += sec("Risks", list(b.risks));
    if (b.catalysts && b.catalysts.length) h += sec("Catalysts to watch", list(b.catalysts));
    h += '<p class="sb-foot">🧠 AI-generated · confidence: ' + esc(b.confidence || "?") + " · " +
         esc(b.model || "") + " · " + esc(b.asof || (b.generated_at || "").slice(0, 10)) +
         " · research context only, not a signal</p>";
    body.innerHTML = h;
    panel.style.display = "";                                    // reveal only on success
  }

  // Called with the filesystem-safe ticker stem (e.g. AAPL, GC_F). Hides the panel
  // first so switching tickers never shows a stale brief, then reveals on success.
  window.loadStockBrief = function (safe) {
    var panel = document.getElementById("stock-brief");
    if (panel) panel.style.display = "none";
    fetch("stockbrief/" + encodeURIComponent(safe) + ".json?_=" + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(render)
      .catch(function () { /* absent/offline -> panel stays hidden */ });
  };
})();
