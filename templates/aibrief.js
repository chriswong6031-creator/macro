/* aibrief.js — the cortex (overnight AI deliberation) panel ONLY.

   ABX v2: the three lens brief bodies (macro / china / btc) are now SERVER-rendered
   into the page by the shared Jinja macro (templates/_aibrief_body.html.j2), so this
   file no longer fetches or renders briefs. It handles just Panel D below.

   Panel D (cortex deliberation, ADB-R7) is client-side: fetches
   site/neuralweb/cortex_memo.json and renders honest degraded copy when the overnight
   deliberation didn't run (the usual state — rate-limited). No synthetic content is
   ever generated; all output is escaped before insertion (no raw HTML). */
(function () {
  function esc(s) { var d = document.createElement("div"); d.textContent = (s == null ? "" : String(s)); return d.innerHTML; }

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
