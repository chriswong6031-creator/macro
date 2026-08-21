/* ══════════════════════════════════════════════════════════════════════════════
   R3B REFERENCE HARNESS — runtime shim.
   Authored for XPV2-SC-R3B (Sector Central six-view reference artifact).

   PURE TRANSPORT, never authority. This file never computes a rank, a lane
   assignment, a count (other than mirroring the SAME `.length`-over-the-full-list
   the production template performs), a state, or a gate decision. It resolves
   fetches/navigations against the embedded data registry, records every
   resolution, and reimplements two small pieces of boot-time behavior
   (`resolveThemeHash`, the tier-hydration insert-by-lane mechanics) that live
   inline in `templates/sector_central.html.j2` and are therefore NOT part of the
   verbatim `templates/si_workspace.js` router this artifact also embeds.

   Loads AFTER the embedded data registry (the REF:DATA slot), BEFORE the
   verbatim router (the REF:ROUTER slot) — see build/README_BUILD.md
   "Assembly order".
   ══════════════════════════════════════════════════════════════════════════════ */
(function(){
'use strict';

var REF = window.REF = window.REF || {};
REF.registry = {};      // production-relative path -> raw embedded text (JSON or JS)
REF.fragments = {};     // production-relative path -> raw embedded HTML fragment text
REF.log = [];           // [{seq, type:'fetch'|'nav'|'boot', path, result}]
REF.simulateFetchFail = false;
REF.accessState = 'gated';  // 'gated' | 'hydrated' | 'ungated'
var _seq = 0;

/* ── 1. Build the registry from the DATA slot's embedded <script> blocks ─────── */
Array.prototype.forEach.call(
  document.querySelectorAll('script[type="application/json"][data-path]'),
  function(el){ REF.registry[el.getAttribute('data-path')] = el.textContent; }
);
Array.prototype.forEach.call(
  document.querySelectorAll('script[type="text/x-ref-fragment"][data-path]'),
  function(el){ REF.fragments[el.getAttribute('data-path')] = el.textContent; }
);

function record(type, path, result){
  _seq += 1;
  REF.log.push({seq:_seq, type:type, path:path, result:result});
  renderLog();
}
REF.recordFetch = function(path, result){ record('fetch', path, result); };
REF.recordNav = function(path, result){ record('nav', path, result === undefined ? 'recorded' : result); };

/* ── 2. window.fetch interception ─────────────────────────────────────────────
   Any fetch the page/router code issues (production's __siFetch, a lazy-mounted
   organ's own fetch, anything) resolves against the registry by
   production-relative path. A path with no embedded entry is a genuine
   rejection — "recorded-not-executed" — so production's own error-state code
   (the __siBoot catch, a lazy organ's own fail-soft branch) runs for real,
   never a faked success. */
function normalizePath(url){
  var p = String(url == null ? '' : url);
  var qi = p.indexOf('?'); if(qi >= 0) p = p.slice(0, qi);
  var hi = p.indexOf('#'); if(hi >= 0) p = p.slice(0, hi);
  if(p.indexOf('./') === 0) p = p.slice(2);
  while(p.indexOf('/') === 0) p = p.slice(1);
  return p;
}
var _hasNativeFetch = typeof window.fetch === 'function';
window.fetch = function(input, init){
  var url = (typeof input === 'string') ? input : (input && input.url) || '';
  var path = normalizePath(url);
  if(REF.simulateFetchFail){
    REF.recordFetch(path, 'simulated-fail');
    return Promise.reject(new TypeError('REF harness: simulate-fetch-fail is ON — rejecting ' + path));
  }
  if(Object.prototype.hasOwnProperty.call(REF.registry, path)){
    REF.recordFetch(path, 'hit');
    var text = REF.registry[path];
    try{
      return Promise.resolve(new Response(text, {status:200, statusText:'OK (embedded)',
        headers:{'Content-Type':'application/json'}}));
    }catch(e){
      /* Response ctor unsupported in this shell — degrade to a fetch-shaped object */
      return Promise.resolve({ok:true, status:200,
        json:function(){ return Promise.resolve(JSON.parse(text)); },
        text:function(){ return Promise.resolve(text); }});
    }
  }
  REF.recordFetch(path, 'recorded-not-executed');
  return Promise.reject(new TypeError('REF harness: no embedded artifact for ' + path +
    ' (recorded-not-executed — e.g. Time Machine episode/chunk fetches; see README_BUILD.md)'));
};
REF.fetchJSON = function(path){
  return window.fetch(path).then(function(r){ if(!r.ok) throw new Error('not ok'); return r.json(); });
};

/* Some producer artifacts (basketdata/action_board.json, at minimum) are
   serialized by Python's json module with `allow_nan=True` (its default),
   which emits BARE `NaN`/`Infinity`/`-Infinity` tokens — valid Python-JSON,
   invalid strict JSON (RFC 8259). Every embedded <script type="application/json">
   block still carries those bytes VERBATIM (no re-serialization, per the
   frozen spec) — this helper exists only so client-side code (this harness's
   view partials, and any production code that would hit the identical bytes)
   can still call JSON.parse on the text. NaN/Infinity fields become `null`,
   meaning "no value" — never a fabricated number, never a sign flip. This is
   the SAME failure a real browser's `r.json()` would hit on the identical
   bytes over a real fetch; the helper does not change what production ships,
   only what this reference artifact's OWN display code can parse. */
REF.parseJSON = function(text){
  var safe = String(text).replace(/:(\s*)NaN\b/g, ':$1null')
                          .replace(/:(\s*)-?Infinity\b/g, ':$1null');
  return JSON.parse(safe);
};

/* ── 3. Navigation recorder ──────────────────────────────────────────────────
   `data-ref-nav` anchors carry their REAL production href (basket/<id>.html,
   stock.html#<TICKER>, subsector/b-uranium.html, rotation/<key>.html, …) so the
   markup itself stays truthful; this delegate intercepts the click instead of
   letting the browser navigate away from the quarantined artifact. In-page
   hashes (#overview, #confluence, legacy anchors, #theme-*, #read-*) carry NO
   data-ref-nav attribute and are untouched — they run through the verbatim
   router exactly as production would. */
REF.nav = function(href){
  REF.recordNav(href, 'recorded (would navigate to ' + href + ')');
  return false;
};
document.addEventListener('click', function(e){
  var a = e.target && e.target.closest ? e.target.closest('a[data-ref-nav]') : null;
  if(!a) return;
  e.preventDefault();
  REF.nav(a.getAttribute('href') || '');
}, true);

/* ── 4. resolveThemeHash() reimplementation ──────────────────────────────────
   Faithful to templates/sector_central.html.j2:2813-2818. NOT part of the
   verbatim si_workspace.js router (that file explicitly refuses #theme-* and
   defers to "the resolver" — routing_contract.md §3). `location.replace(...)`
   becomes a recorded navigation instead of an actual page leave. Boot-only,
   exactly as production's own single call site
   (`if(location.hash.startsWith('#theme-')) resolveThemeHash();`) — never
   re-invoked from hashchange (that IS the recorded seam (a) in
   routing_contract.md §8 and this shim preserves it, not repairs it). */
REF._basketsCache = null;
function loadBasketsSync(){
  /* Synchronous JSON.parse of the verbatim embedded bytes — not a recompute
     (no field is derived, filtered, or re-ranked), just the same JSON.parse a
     browser's `r.json()` would perform on the identical bytes over a real
     fetch. Needed synchronously because resolveThemeHash() must be able to
     answer themeById() at BOOT, before any Promise microtask would flush. */
  if(REF._basketsCache) return REF._basketsCache;
  var raw = REF.registry['basketdata/baskets.json'];
  if(!raw) return null;
  try{
    var parsed = JSON.parse(raw);
    REF._basketsCache = parsed;
    window.BASKETS = parsed;
    window.THEME = parsed.theme_intel || null;
    record('boot', 'basketdata/baskets.json', 'hit (sync boot parse)');
    return parsed;
  }catch(e){ return null; }
}
REF.themeById = function(id){
  /* Mirrors templates/sector_central.html.j2:2877 themeById() exactly:
     ((THEME&&THEME.themes)||[]).find(t=>t&&t.id===id)||null */
  var b = loadBasketsSync();
  var themes = (b && b.theme_intel && b.theme_intel.themes) || [];
  for(var i=0;i<themes.length;i++){ if(themes[i] && themes[i].id === id) return themes[i]; }
  return null;
};
function resolveThemeHash(){
  var id = (location.hash || '').slice(7);
  try{ id = decodeURIComponent(id); }catch(e){}
  if(!id || !REF.themeById(id)) return;
  REF.nav('basket/' + encodeURIComponent(id) + '.html');
}
if((location.hash || '').indexOf('#theme-') === 0) resolveThemeHash();

/* ── 5. Scroll-offset law ─────────────────────────────────────────────────────
   Every anchor/legacy-target id needs scroll-margin-top equal to the real
   sticky-chrome height, or a hash landing buries its target under the topbar.
   shell.html declares the CSS var with a static fallback and the rule that
   consumes it (`[id]{scroll-margin-top:var(--ref-sticky-offset)}`); this shim
   overwrites the var with the MEASURED height of the actual rendered sticky
   header once it exists, so the placeholder (and any later design-lane shell
   dropped into the same slot) stays correct regardless of its real height. */
function wireStickyOffset(){
  var bar = document.querySelector('.si-topbar');
  var h = bar ? Math.ceil(bar.getBoundingClientRect().height) : 56;
  document.documentElement.style.setProperty('--ref-sticky-offset', h + 'px');
}

/* ── 6. Access-state board (Overview Act-Now) hook ───────────────────────────
   overview.html registers REF.renderActNow(state) on DOMContentLoaded. This
   shim only owns the SELECTOR and the state variable — the actual per-lane
   rendering (gated preview slice / hydrated insert-by-data-ab-lane / ungated
   full lists) lives with the Overview view partial, which is the file that
   owns the #actnow DOM the state applies to. */
REF.setAccessState = function(state){
  REF.accessState = state;
  if(typeof REF.renderActNow === 'function') REF.renderActNow(state);
  record('boot', '(access-state)', state);
};

/* ── 7. The drawer — quarantine chrome, deliberately plain ───────────────────
   "R3 REFERENCE HARNESS — not product UI." EN-only per the commission. Never
   styled to look like a product surface; a design lane replacing shell.html
   must not be tempted to reuse this chrome as-is. */
var STYLE = '' +
'#ref-harness{position:fixed;right:0;bottom:0;z-index:99999;max-width:360px;' +
  'font:12px/1.4 ui-monospace,Menlo,Consolas,monospace;background:#1a1a1a;color:#e0e0e0;' +
  'border:2px solid #ff8c00;border-radius:6px 0 0 0;box-shadow:0 0 0 9999px transparent;}' +
'#ref-harness.collapsed #ref-harness-body{display:none;}' +
'#ref-harness-head{display:flex;align-items:center;justify-content:space-between;gap:8px;' +
  'padding:6px 8px;background:#ff8c00;color:#1a1a1a;font-weight:700;cursor:pointer;' +
  'border-radius:4px 0 0 0;}' +
'#ref-harness-body{padding:8px;max-height:60vh;overflow:auto;}' +
'#ref-harness .rf-row{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:4px 0;}' +
'#ref-harness select,#ref-harness button{font:inherit;background:#2a2a2a;color:#e0e0e0;' +
  'border:1px solid #555;border-radius:3px;padding:2px 4px;}' +
'#ref-harness button.on{background:#ff8c00;color:#1a1a1a;border-color:#ff8c00;}' +
'#ref-harness-log{list-style:none;margin:6px 0 0;padding:0;border-top:1px solid #444;}' +
'#ref-harness-log li{padding:2px 0;border-bottom:1px dashed #333;word-break:break-all;}' +
'#ref-harness-log li.miss{color:#ff6b6b;}' +
'#ref-harness-log li.nav{color:#6bb8ff;}' +
'#ref-harness-log li.hit{color:#8fd68f;}';
var styleEl = document.createElement('style');
styleEl.id = 'ref-harness-style';
styleEl.textContent = STYLE;
document.head.appendChild(styleEl);

var HTML = '' +
'<div id="ref-harness" class="collapsed">' +
  '<div id="ref-harness-head">' +
    '<span>R3 REFERENCE HARNESS — not product UI</span>' +
    '<span id="ref-harness-toggle">▲</span>' +
  '</div>' +
  '<div id="ref-harness-body">' +
    '<div class="rf-row"><label for="ref-lang">Language</label>' +
      '<select id="ref-lang"><option value="en">en</option><option value="zh">zh</option></select></div>' +
    '<div class="rf-row"><label for="ref-theme">Theme</label>' +
      '<select id="ref-theme"><option value="dark">dark</option><option value="light">light</option></select></div>' +
    '<div class="rf-row"><label for="ref-access">Access state</label>' +
      '<select id="ref-access"><option value="gated">gated</option>' +
        '<option value="hydrated">hydrated</option><option value="ungated">ungated</option></select></div>' +
    '<div class="rf-row"><label for="ref-failfetch">Simulate fetch fail</label>' +
      '<button id="ref-failfetch" type="button" aria-pressed="false">off</button></div>' +
    '<div class="rf-row"><strong>Recorder</strong><button id="ref-log-clear" type="button">clear</button></div>' +
    '<ul id="ref-harness-log"></ul>' +
  '</div>' +
'</div>';
document.addEventListener('DOMContentLoaded', function(){
  document.body.insertAdjacentHTML('beforeend', HTML);
  wireStickyOffset();

  var root = document.getElementById('ref-harness');
  document.getElementById('ref-harness-head').addEventListener('click', function(){
    root.classList.toggle('collapsed');
    document.getElementById('ref-harness-toggle').textContent = root.classList.contains('collapsed') ? '▲' : '▼';
  });
  document.getElementById('ref-lang').addEventListener('change', function(e){
    document.documentElement.setAttribute('data-lang', e.target.value);
    try{ document.dispatchEvent(new CustomEvent('langchange')); }catch(err){}
  });
  document.getElementById('ref-theme').addEventListener('change', function(e){
    document.documentElement.setAttribute('data-theme', e.target.value);
  });
  document.getElementById('ref-access').addEventListener('change', function(e){
    REF.setAccessState(e.target.value);
  });
  document.getElementById('ref-failfetch').addEventListener('click', function(e){
    REF.simulateFetchFail = !REF.simulateFetchFail;
    e.target.textContent = REF.simulateFetchFail ? 'on' : 'off';
    e.target.setAttribute('aria-pressed', String(REF.simulateFetchFail));
    e.target.classList.toggle('on', REF.simulateFetchFail);
  });
  document.getElementById('ref-log-clear').addEventListener('click', function(){
    REF.log.length = 0; renderLog();
  });
  renderLog();
});

function renderLog(){
  var ul = document.getElementById('ref-harness-log');
  if(!ul) return; // drawer not mounted yet — render() is re-invoked from DOMContentLoaded
  var rows = REF.log.slice(-200).map(function(e){
    var cls = e.type === 'nav' ? 'nav' : (e.result === 'hit' || (e.result && e.result.indexOf('hit') === 0) ? 'hit' : 'miss');
    return '<li class="' + cls + '">#' + e.seq + ' [' + e.type + '] ' + e.path + ' — ' + e.result + '</li>';
  });
  ul.innerHTML = rows.join('');
}
REF.renderLog = renderLog;

})();
