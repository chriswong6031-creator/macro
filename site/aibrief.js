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
   loads; all LLM output is escaped before insertion (no raw HTML).

   Panel D (cortex deliberation, ADB-R7) is client-side: fetches
   neuralweb/cortex_memo.json and renders honest degraded copy when the overnight
   deliberation didn't run (the usual state — rate-limited). No synthetic content is
   ever generated. */
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
    // Degraded state: render explicitly per spec §2.4 (not silently hidden).
    if (b.degraded_reason && !b.regime_read) {
      var lang2 = document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en";
      body.innerHTML = '<p class="mb-deg">' + esc(
        lang2 === "zh"
          ? "AI 简报不可用（确定性模式）· " + b.degraded_reason
          : "AI brief unavailable (deterministic only) · " + b.degraded_reason
      ) + "</p>";
      panel.style.display = "";
      return;
    }
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

  // ── Panel D: Cortex deliberation (ADB-R7) ────────────────────────────────────
  // Fetch site/neuralweb/cortex_memo.json. If degraded (the steady state): render
  // one honest line. If non-degraded: render labeled AI-deliberation block with
  // as_of, what_fired, and deserves_operator. Never emit synthetic content.
  (function loadCortex() {
    var panel = document.getElementById("cortex-panel");
    var body  = document.getElementById("cortex-body");
    if (!panel || !body) return;

    fetch("neuralweb/cortex_memo.json?_=" + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (memo) {
        if (!memo) return; // absent → panel stays hidden

        var lang = document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en";
        var status = (memo.run_status || {}).status || "degraded";
        var asOf   = memo.as_of || "";

        if (status === "degraded") {
          // Honest degraded copy — no synthetic content (ADB-R7)
          body.innerHTML = '<p class="mb-deg">' + esc(
            lang === "zh"
              ? "隔夜AI复盘遭速率限制，未能运行。以上简报完全基于确定性看板。"
              : "The overnight AI deliberation was rate-limited and did not run. " +
                "The brief above stands on the deterministic dashboards alone."
          ) + (asOf ? ' <span class="muted" style="font-size:11px">(' + esc(asOf.slice(0, 10)) + ')</span>' : "") + "</p>";
        } else {
          // Non-degraded: render labeled AI-deliberation block
          var h = '<div class="cortex-label">' + esc(
            lang === "zh" ? "AI 复盘输出 — 非交易信号" : "AI DELIBERATION OUTPUT — NOT A SIGNAL"
          ) + "</div>";

          if (asOf) {
            h += '<p class="muted sm" style="margin:0 0 6px">' +
              esc(lang === "zh" ? "复盘时间：" : "As of: ") +
              esc(asOf.slice(0, 16).replace("T", " ") + " UTC") + "</p>";
          }

          var summary = memo.summary || "";
          if (summary) {
            h += '<div class="cortex-section"><div class="cortex-h">' +
              esc(lang === "zh" ? "总结" : "What the overnight AI reviewer flagged") +
              "</div><p style='font-size:13px;margin:0'>" + esc(summary) + "</p></div>";
          }

          var whatFired = memo.what_fired || [];
          if (whatFired.length) {
            h += '<div class="cortex-section"><div class="cortex-h">' +
              esc(lang === "zh" ? "触发项" : "Flagged items") + "</div><ul class='cortex-list'>" +
              whatFired.map(function (x) { return "<li>" + esc(String(x)) + "</li>"; }).join("") +
              "</ul></div>";
          }

          var deserves = memo.deserves_operator || [];
          if (deserves.length) {
            h += '<div class="cortex-section"><div class="cortex-h">' +
              esc(lang === "zh" ? "需要关注" : "Items that deserve your attention") +
              "</div><ul class='cortex-list'>" +
              deserves.map(function (x) { return "<li>" + esc(String(x)) + "</li>"; }).join("") +
              "</ul></div>";
          }

          // Render optional forward_watch keys if present (W1/W2, absent today)
          var fw = memo.forward_watch || [];
          if (fw.length) {
            h += '<div class="cortex-section"><div class="cortex-h">' +
              esc(lang === "zh" ? "前瞻关注" : "Forward watch") + "</div><ul class='cortex-list'>" +
              fw.map(function (row) {
                return "<li>" + esc(row.date || "") + " — " + esc(row.label || String(row)) + "</li>";
              }).join("") + "</ul></div>";
          }

          body.innerHTML = h;
        }

        panel.style.display = "";  // reveal panel only after content is set
      })
      .catch(function () { /* fetch error → panel stays hidden */ });
  })();
})();
