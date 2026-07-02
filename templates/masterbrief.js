/* Master Brief panel — fetches the AI cross-asset synthesis (master_brief.json,
   written by engine/master_brain.py). RESEARCH CONTEXT ONLY — never a signal.
   Bilingual: renders English, or the DeepSeek-translated Chinese (brief.zh) when the
   site is toggled to 中文, re-rendering on the 'langchange' event (per-field fallback
   to English if a translation is missing). Hidden until a usable brief loads; LLM
   output is escaped before insertion (no raw HTML). */
(function () {
  var BRIEF = null;
  var LBL = {
    en: { regime: "Regime read", conflicts: "Conflicts", rotation: "Rotation thesis",
          transmission: "Transmission chains to watch", watch: "Watch next",
          conf: "confidence", foot: "context only, not a signal" },
    zh: { regime: "宏观格局解读", conflicts: "信号冲突", rotation: "轮动假设检验",
          transmission: "传导链关注", watch: "后续关注",
          conf: "可信度", foot: "仅供研究参考，非交易信号" },
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
  function list(a) { return '<ul class="mb-list">' + a.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>"; }
  function sec(title, body) { return '<div class="mb-sec"><div class="mb-h">' + esc(title) + "</div>" + body + "</div>"; }

  function render() {
    var panel = document.getElementById("master-brief");
    var body = document.getElementById("master-brief-body");
    if (!panel || !body || !BRIEF) return;
    var b = BRIEF;
    // Degraded state: explicit render per spec §2.4 (degraded output is ABSENT, not neutral;
    // surfaces must render their state, not stay silently hidden).
    if (b.degraded_reason && !b.regime_read) {
      body.innerHTML = '<p class="mb-deg">' + esc(
        curLang() === "zh"
          ? "AI 简报不可用（确定性模式）· " + b.degraded_reason
          : "AI brief unavailable (deterministic only) · " + b.degraded_reason
      ) + "</p>";
      panel.style.display = "";
      return;
    }
    var lang = curLang(), t = LBL[lang];
    var summary = pick(b, lang, "summary"), regime = pick(b, lang, "regime_read"),
        rotation = pick(b, lang, "rotation_check"),
        conflicts = pickList(b, lang, "conflicts"),
        transmission = pickList(b, lang, "transmission"),
        watch = pickList(b, lang, "watch_items");
    var h = "";
    if (summary) h += '<p class="mb-sum">' + esc(summary) + "</p>";
    if (regime) h += sec(t.regime, "<p>" + esc(regime) + "</p>");
    if (conflicts && conflicts.length) h += sec(t.conflicts, list(conflicts));
    if (rotation) h += sec(t.rotation, "<p>" + esc(rotation) + "</p>");
    if (transmission && transmission.length) h += sec(t.transmission, list(transmission));
    if (watch && watch.length) h += sec(t.watch, list(watch));
    h += '<p class="mb-foot">' + esc(t.conf) + ": " + esc(b.confidence || "?") + " · " +
         esc(b.model || "") + " · " + esc(b.state_asof || "") + " · " + esc(t.foot) + "</p>";
    body.innerHTML = h;
    panel.style.display = "";                           // reveal only on success
  }

  fetch("master_brief.json?_=" + Date.now())
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (b) { BRIEF = b; render(); })
    .catch(function () { /* absent/offline -> panel stays hidden */ });
  document.addEventListener("langchange", render);     // re-render on the EN/中文 toggle
})();
