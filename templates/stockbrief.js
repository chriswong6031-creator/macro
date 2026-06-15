/* Single-stock AI brief panel — fetches site/stockbrief/<safe>.json (precomputed
   by engine/catalyst_stock.py). RESEARCH CONTEXT ONLY — never a signal. The panel
   stays hidden unless a usable brief loads (so it's invisible when the feature is
   off or the ticker wasn't precomputed). All model output is escaped before
   insertion — no raw HTML is ever trusted from the JSON. Bilingual: renders English,
   or the DeepSeek-translated Chinese (brief.zh) under the 中文 toggle, re-rendering on
   'langchange'. Exposes window.loadStockBrief(safe), called by stock.html's load(). */
(function () {
  var BRIEF = null;
  var LBL = {
    en: { drivers: "Drivers", risks: "Risks", catalysts: "Catalysts to watch",
          ai: "AI-generated", conf: "confidence", foot: "research context only, not a signal" },
    zh: { drivers: "驱动因素", risks: "风险", catalysts: "关注催化",
          ai: "AI 生成", conf: "可信度", foot: "仅供研究参考，非交易信号" },
  };
  function esc(s) { var d = document.createElement("div"); d.textContent = (s == null ? "" : String(s)); return d.innerHTML; }
  function curLang() { return document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en"; }
  function pick(b, lang, k) {
    if (lang === "zh" && b.zh && b.zh[k] != null && b.zh[k] !== "") return b.zh[k];
    return b[k];
  }
  function pickList(b, lang, k) {
    var en = b[k] || [];
    if (lang === "zh" && b.zh && Array.isArray(b.zh[k])) {
      return en.map(function (e, i) { var z = b.zh[k][i]; return (z != null && z !== "") ? z : e; });
    }
    return en;
  }
  function list(a) { return '<ul class="sb-list">' + a.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>"; }
  function sec(title, body) { return '<div class="sb-sec"><div class="sb-h">' + esc(title) + "</div>" + body + "</div>"; }
  function usable(b) {
    return b && (b.summary || (b.drivers && b.drivers.length) ||
                 (b.risks && b.risks.length) || (b.catalysts && b.catalysts.length));
  }

  function render() {
    var panel = document.getElementById("stock-brief");
    var body = document.getElementById("stock-brief-body");
    if (!panel || !body) return;
    var b = BRIEF;
    if (!usable(b)) { panel.style.display = "none"; return; }   // degraded/empty -> stay hidden
    var lang = curLang(), t = LBL[lang];
    var summary = pick(b, lang, "summary"),
        drivers = pickList(b, lang, "drivers"),
        risks = pickList(b, lang, "risks"),
        catalysts = pickList(b, lang, "catalysts");
    var h = "";
    if (summary) h += '<p class="sb-sum">' + esc(summary) + "</p>";
    if (drivers && drivers.length) h += sec(t.drivers, list(drivers));
    if (risks && risks.length) h += sec(t.risks, list(risks));
    if (catalysts && catalysts.length) h += sec(t.catalysts, list(catalysts));
    h += '<p class="sb-foot">🧠 ' + esc(t.ai) + " · " + esc(t.conf) + ": " + esc(b.confidence || "?") +
         " · " + esc(b.model || "") + " · " + esc(b.asof || (b.generated_at || "").slice(0, 10)) +
         " · " + esc(t.foot) + "</p>";
    body.innerHTML = h;
    panel.style.display = "";                                    // reveal only on success
  }

  // Called with the filesystem-safe ticker stem (e.g. AAPL, GC_F). Hides the panel
  // first so switching tickers never shows a stale brief, then reveals on success.
  window.loadStockBrief = function (safe) {
    var panel = document.getElementById("stock-brief");
    if (panel) panel.style.display = "none";
    BRIEF = null;
    fetch("stockbrief/" + encodeURIComponent(safe) + ".json?_=" + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (b) { BRIEF = b; render(); })
      .catch(function () { /* absent/offline -> panel stays hidden */ });
  };
  document.addEventListener("langchange", render);     // re-render the current brief on the EN/中文 toggle
})();
