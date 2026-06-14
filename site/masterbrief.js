/* Master Brief panel — fetches the AI cross-asset synthesis (master_brief.json,
   written by engine/master_brain.py). RESEARCH CONTEXT ONLY — never a signal.
   The panel stays hidden until a usable brief loads (so it's invisible when the
   feature is off). LLM output is escaped before insertion (no raw HTML). */
(function () {
  function esc(s) { var d = document.createElement("div"); d.textContent = (s == null ? "" : String(s)); return d.innerHTML; }
  function list(a) { return '<ul class="mb-list">' + a.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>"; }
  function sec(title, body) { return '<div class="mb-sec"><div class="mb-h">' + esc(title) + "</div>" + body + "</div>"; }

  function render(b) {
    var panel = document.getElementById("master-brief");
    var body = document.getElementById("master-brief-body");
    if (!panel || !body) return;
    if (!b || (b.degraded_reason && !b.regime_read)) return;   // no usable brief -> stay hidden
    var h = "";
    if (b.summary) h += '<p class="mb-sum">' + esc(b.summary) + "</p>";
    if (b.regime_read) h += sec("Regime read", "<p>" + esc(b.regime_read) + "</p>");
    if (b.conflicts && b.conflicts.length) h += sec("Conflicts", list(b.conflicts));
    if (b.rotation_check) h += sec("Rotation thesis", "<p>" + esc(b.rotation_check) + "</p>");
    if (b.transmission && b.transmission.length) h += sec("Transmission chains to watch", list(b.transmission));
    if (b.watch_items && b.watch_items.length) h += sec("Watch next", list(b.watch_items));
    h += '<p class="mb-foot">confidence: ' + esc(b.confidence || "?") + " · " + esc(b.model || "") +
         " · " + esc(b.state_asof || "") + " · context only, not a signal</p>";
    body.innerHTML = h;
    panel.style.display = "";                                    // reveal only on success
  }

  fetch("master_brief.json?_=" + Date.now())
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(render)
    .catch(function () { /* absent/offline -> panel stays hidden */ });
})();
