/* aibrief.js — renders focused AI briefs (china_brief.json / btc_brief.json, written
   by engine/master_brain.py) into any .ai-brief panel on the page. RESEARCH CONTEXT
   ONLY — never a signal. Each panel declares its source + body target via attributes:

     <div class="... ai-brief" data-brief-src="china_brief.json" style="display:none">
       <div data-brief-body></div>
     </div>

   Bilingual the same way the rest of the page is: every text is emitted as a dual
   <span class="l-en">EN</span><span class="l-zh">ZH</span> pair and the page CSS shows
   whichever language is active — so no langchange wiring is needed (per-field fallback
   to English when a translation is missing). Panels stay hidden until a usable brief
   loads; all LLM output is escaped before insertion (no raw HTML). */
(function () {
  var LBL = {
    regime: ["Regime read", "格局解读"],
    conflicts: ["Conflicts", "信号冲突"],
    rotation: ["Thesis check", "假设检验"],
    transmission: ["Transmission chains to watch", "传导链关注"],
    watch: ["Watch next", "后续关注"],
    conf: ["confidence", "可信度"],
    foot: ["context only, not a signal", "仅供研究参考，非交易信号"],
  };
  function esc(s) { var d = document.createElement("div"); d.textContent = (s == null ? "" : String(s)); return d.innerHTML; }
  // dual-language span; the page's existing l-en/l-zh CSS toggles which one shows.
  function bi(en, zh) {
    var z = (zh != null && zh !== "") ? zh : en;
    return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' + esc(z) + "</span>";
  }
  function lbl(k) { return bi(LBL[k][0], LBL[k][1]); }
  function field(b, k) { return bi(b[k], b.zh && b.zh[k]); }
  function listField(b, k) {
    var en = b[k] || [], zh = (b.zh && b.zh[k]) || [];
    return '<ul class="mb-list">' + en.map(function (e, i) { return "<li>" + bi(e, zh[i]) + "</li>"; }).join("") + "</ul>";
  }
  function sec(labelHtml, body) { return '<div class="mb-sec"><div class="mb-h">' + labelHtml + "</div>" + body + "</div>"; }

  function render(panel, b) {
    var body = panel.querySelector("[data-brief-body]");
    if (!body || !b) return;
    if (b.degraded_reason && !b.regime_read) return;   // nothing usable -> stay hidden
    var h = "";
    if (b.summary) h += '<p class="mb-sum">' + field(b, "summary") + "</p>";
    if (b.regime_read) h += sec(lbl("regime"), "<p>" + field(b, "regime_read") + "</p>");
    if (b.conflicts && b.conflicts.length) h += sec(lbl("conflicts"), listField(b, "conflicts"));
    if (b.rotation_check) h += sec(lbl("rotation"), "<p>" + field(b, "rotation_check") + "</p>");
    if (b.transmission && b.transmission.length) h += sec(lbl("transmission"), listField(b, "transmission"));
    if (b.watch_items && b.watch_items.length) h += sec(lbl("watch"), listField(b, "watch_items"));
    h += '<p class="mb-foot">' + lbl("conf") + ": " + esc(b.confidence || "?") + " · " +
         esc(b.model || "") + " · " + esc(b.state_asof || "") + " · " + lbl("foot") + "</p>";
    body.innerHTML = h;
    panel.style.display = "";                            // reveal only on success
  }

  function load(panel) {
    var src = panel.getAttribute("data-brief-src");
    if (!src) return;
    fetch(src + "?_=" + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (b) { if (b) render(panel, b); })
      .catch(function () { /* absent/offline -> panel stays hidden */ });
  }

  var panels = document.querySelectorAll(".ai-brief[data-brief-src]");
  for (var i = 0; i < panels.length; i++) load(panels[i]);
})();
