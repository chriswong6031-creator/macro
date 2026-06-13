# Macro nav redesign — handoff spec

**For the session that owns the macro nav / i18n / sections overhaul.**
Built & browser-verified by a parallel session 2026-06-13; handed off (not applied
to the page templates) to avoid clobbering your in-flight nav expansion.

## What this delivers (user request)
1. Reorganize the messy macro menu into one clean bar: **section links · global
   stock search · animated theme toggle · animated language toggle**.
2. Dark/Light becomes an **animated sliding switch** (not a button).
3. EN/中文 becomes an **animated segmented toggle** (not a button).
4. The "🔎 Any stock" link becomes a **live search bar** in the nav; picking a
   result **bounces to the stock analyzer** (`stock.html#TICKER`).
5. Same nav, same search position, on **every macro page** (macro dashboard,
   history, sectors, brief, stock analyzer — and your new ETF-flows / China /
   Commodities pages). **Do NOT touch Bitcoin Vector / hub** (separate menu, later).

## Status — foundation is DONE and lives in the shared assets
The CSS and JS are already added to the working tree and are **backward-compatible**
(the legacy `.theme-btn` / `.lang-btn` text buttons on Vector/hub/China keep working):

- `templates/theme.css` — block `/* ===== unified macro nav ===== */`:
  `.site-nav`, `.nav-link`, `.nav-search` (+ `.nav-sugg` autocomplete dropdown),
  `.theme-switch` (animated), `.lang-toggle` (animated). All themed via existing
  CSS vars; the toggles animate **purely off `html[data-theme]` / `html[data-lang]`**.
- `templates/theme.js` — added `initNavSearch()` (autocomplete + bounce), wired
  `.theme-switch` → `toggleTheme` and `.lang-toggle .opt` → `setLang`, and exposed
  `window.setLang` / `window.setTheme`. **The existing `data-lang` / `langchange`
  / chart-relabel mechanism is untouched** — the new toggles just flip the same
  attributes your i18n already keys off.

**Verified in-browser** on `macro.html`: toggles slide and re-theme; typing "NVD"
→ click → navigated to `stock.html#NVDA` and the analyzer rendered "Nvidia Corp
(NVDA)"; search shows tinted state chips reusing the `.st-*` badge classes.

If your rebuilds dropped the `theme.css` / `theme.js` additions, re-apply them from
the **Appendix** below (they are idempotent and additive).

## All that remains: place the nav markup + remove the old nav

### 1. The nav block (root-level pages: macro, history, stock, brief)
Put it as the **first element inside `<body>`** (above the content panels), and
**delete the old nav controls** from each page's `.topline` (the `navbtn` links +
`.lang-btn` + `.theme-btn`). Keep page content (h1, badges) in the panel.

```html
<nav class="site-nav">
  <div class="nav-links">
    <a class="nav-link" href="index.html">🏠 {{ t('Home','首页') }}</a>
    <a class="nav-link" href="macro.html">📊 {{ t('Macro','宏观') }}</a>
    <a class="nav-link" href="vector.html">₿ {{ t('Bitcoin Vector','比特币向量') }}</a>
    <a class="nav-link" href="etfs.html">🐳 {{ t('ETF flows','ETF 资金流') }}</a>
    <a class="nav-link" href="brief.html">📰 {{ t('Brief','简报') }}</a>
    <a class="nav-link" href="history.html">📈 {{ t('History','历史') }}</a>
  </div>
  <div class="nav-search">
    <span class="mag">🔎</span>
    <input type="text" autocomplete="off" aria-label="Search stocks"
      placeholder="{{ t('Search any stock, ETF, commodity or crypto…','搜索任意股票、ETF、商品或加密货币…') }}">
    <div class="nav-sugg"></div>
  </div>
  <div class="nav-ctrls">
    <button class="theme-switch" aria-label="{{ t('Toggle dark / light mode','切换深色／浅色模式') }}">
      <span class="ic sun">☀️</span><span class="ic moon">🌙</span><span class="knob"></span>
    </button>
    <div class="lang-toggle" role="group" aria-label="Language">
      <span class="pill"></span>
      <span class="opt en-opt" data-l="en">EN</span>
      <span class="opt zh-opt" data-l="zh">中文</span>
    </div>
  </div>
</nav>
```

- **Active link:** add ` active` to the current page's `.nav-link`
  (e.g. `class="nav-link active"` on `macro.html` for the Macro dashboard,
  `history.html` for History, etc.). Stock/sector pages can leave none active.
- **Your new sections:** add/remove `<a class="nav-link">` entries freely — China
  A-Shares, Commodities, etc. The bar wraps responsively; the search is the
  flex-grow element. (Drop links you don't want; this set is a suggestion.)

### 2. Sector pages (`templates/sector.html.j2`, output in `/sectors/`)
Use the **same block but prefix every href with `../`**
(`../index.html`, `../macro.html`, `../vector.html`, `../etfs.html`,
`../brief.html`, `../history.html`). The search JS already detects `/sectors/`
and prefixes `../` for `index.json` and the `stock.html#…` bounce automatically —
no JS change needed.

### 3. Stock analyzer (`templates/stock.html.j2`) — user chose "nav search only"
- Add the nav block (root-level hrefs).
- **Remove the in-page search box**: delete the `<div class="searchwrap"><input id="q">
  <div id="sugg"></div></div>` and its intro `<p>`. The nav search bar is now the
  single search everywhere.
- **Remove only the autocomplete half of the page JS** — the `#q` input handler,
  the `#sugg` rendering, and the `idx`/`fetch('stockdata/index.json')` used purely
  for in-page suggestions. **Keep** `load()`, `render()`, `fromHash()`, the
  `hashchange` listener, and the `themechange`/`langchange` re-render hooks — the
  nav search drives everything via the hash.
- Make sure `fromHash()` still runs on load (it was chained after the now-removed
  `index.json` fetch — call it directly on `DOMContentLoaded`).
- Empty state (no hash): show a short "search above to analyze any stock" hint
  instead of the old search box.

### 4. Daily brief (`scripts/daily_brief.py`, non-Jinja f-string)
Replace the `<p><a href="index.html">← dashboard</a> · <button class="lang-btn">…
<button class="theme-btn">…</p>` line with the same `<nav class="site-nav">…</nav>`
block (translate the `t(...)` calls into the inline `<span class="l-en">/<span
class="l-zh">` dual-emit form this file already uses).

### 5. `scripts/build_vector.py` relocation (`VECTOR_NAV`)
`build_landing()` injects `VECTOR_NAV` before the first `.navbtn` when relocating
the dashboard to `macro.html`. With the new nav there are no `.navbtn`s and the
template already contains an `href="vector.html"` link, so **the injection
auto-skips** (its guard is `'href="vector.html"' not in macro_html`). Net: nothing
to do, but verify `macro.html` doesn't get a stray injected button. If you'd rather
inject Home/Vector at relocation than hard-code them in `dashboard.html.j2`, update
`VECTOR_NAV` to emit `<a class="nav-link" …>` instead of `<a class="navbtn" …>`.

## Guardrails
- **Don't touch** `templates/vector.html.j2`, the hub (`_hub_html` in
  `build_vector.py`), or the China pages' menus — they keep the legacy buttons,
  still wired by `theme.js`.
- The toggles need **no JS to update their labels** — never set `.theme-switch` /
  `.lang-toggle` innerHTML; the CSS swaps the knob icon (`🌙`/`☀️`) and slides the
  pill off the root attribute. (Contrast the legacy `.theme-btn`/`.lang-btn`, which
  `theme.js` still relabels.)
- Search reuses `site/stockdata/index.json` (`{t,n,s,st}`) — already built nightly.

## Verification checklist (after you integrate)
- [ ] Nav identical & in the same position on macro / history / stock / sectors / brief.
- [ ] Theme switch slides + re-themes; persists via `localStorage`; charts re-theme.
- [ ] Lang toggle slides; `langchange` still fires (charts/labels translate).
- [ ] Search autocompletes; ↑/↓/Enter/Esc work; click → `stock.html#TICKER` loads.
- [ ] From a sector page, search + links resolve via `../` correctly.
- [ ] Analyzer: no in-page search box; deep-link `stock.html#AAPL` still renders.
- [ ] Both themes × both languages look right on every page.

---

## Appendix A — CSS (already in `templates/theme.css`)
```css
/* ===================== unified macro nav ===================== */
.site-nav { display: flex; align-items: center; gap: 10px; margin: 0 0 16px; flex-wrap: wrap; }
.site-nav .nav-links { display: flex; align-items: center; gap: 2px; flex: none; }
.site-nav a.nav-link { padding: 7px 11px; border-radius: 9px; font-size: 13.5px;
  font-weight: 500; color: var(--muted); text-decoration: none; white-space: nowrap;
  transition: color .18s, background .18s; }
.site-nav a.nav-link:hover, .site-nav a.nav-link.active { color: var(--text); background: var(--panel2); }
.nav-search { position: relative; flex: 1 1 280px; min-width: 150px; max-width: 480px; }
.nav-search .mag { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); font-size: 12px; opacity: .65; pointer-events: none; }
.nav-search input { width: 100%; box-sizing: border-box; padding: 8px 12px 8px 32px; border-radius: 10px;
  border: 1px solid var(--line); background: var(--panel2); color: var(--text); font: inherit; font-size: 13px; outline: none; transition: border-color .18s; }
.nav-search input::placeholder { color: var(--muted); }
.nav-search input:focus { border-color: var(--link); }
.nav-sugg { position: absolute; top: calc(100% + 5px); left: 0; right: 0; z-index: 80; background: var(--panel);
  border: 1px solid var(--line); border-radius: 11px; overflow: hidden; overflow-y: auto; max-height: 60vh;
  box-shadow: var(--popover-shadow); display: none; }
.nav-sugg.show { display: block; }
.nav-sugg .row { display: flex; align-items: center; gap: 9px; padding: 8px 12px; cursor: pointer; }
.nav-sugg .row:hover, .nav-sugg .row.sel { background: var(--panel2); }
.nav-sugg .row b { min-width: 58px; font-size: 13px; color: var(--text); font-weight: 600; }
.nav-sugg .row small { flex: 1; color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nav-sugg .row .stt { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 6px; white-space: nowrap; }
.nav-sugg .empty { padding: 11px 13px; color: var(--muted); font-size: 12.5px; }
.site-nav .nav-ctrls { display: flex; align-items: center; gap: 10px; flex: none; }
.theme-switch { width: 56px; height: 27px; border-radius: 999px; background: var(--panel2); border: 1px solid var(--line); position: relative; cursor: pointer; padding: 0; flex: none; }
.theme-switch .ic { position: absolute; top: 50%; transform: translateY(-50%); font-size: 10.5px; opacity: .5; line-height: 1; }
.theme-switch .ic.sun { left: 8px; } .theme-switch .ic.moon { right: 8px; }
.theme-switch .knob { position: absolute; top: 2px; left: 2px; width: 22px; height: 22px; border-radius: 50%;
  background: #e8c15a; display: flex; align-items: center; justify-content: center; font-size: 11px;
  box-shadow: 0 2px 5px rgba(0,0,0,.3); transition: transform .34s cubic-bezier(.34,1.45,.5,1), background .3s; }
.theme-switch .knob::before { content: "🌙"; }
html[data-theme="light"] .theme-switch .knob { transform: translateX(29px); background: #285fff; }
html[data-theme="light"] .theme-switch .knob::before { content: "☀️"; }
.lang-toggle { display: inline-flex; position: relative; background: var(--panel2); border: 1px solid var(--line); border-radius: 999px; padding: 3px; flex: none; cursor: pointer; }
.lang-toggle .pill { position: absolute; top: 3px; left: 3px; width: calc(50% - 3px); height: calc(100% - 6px); border-radius: 999px; background: var(--link); transition: transform .34s cubic-bezier(.34,1.4,.5,1); }
html[data-lang="zh"] .lang-toggle .pill { transform: translateX(100%); }
.lang-toggle .opt { position: relative; z-index: 1; min-width: 28px; text-align: center; padding: 3px 9px; font-size: 11.5px; font-weight: 600; color: var(--muted); transition: color .25s; user-select: none; }
html:not([data-lang="zh"]) .lang-toggle .en-opt { color: #fff; }
html[data-lang="zh"] .lang-toggle .zh-opt { color: #fff; }
@media (max-width: 760px) { .nav-search { order: 9; flex-basis: 100%; max-width: none; } }
```

## Appendix B — JS (already in `templates/theme.js`)
Added after `window.toggleLang = …`:
```js
window.setLang = setLang;
window.setTheme = setTheme;

function initNavSearch() {
  var box = document.querySelector('.nav-search');
  if (!box) return;
  var input = box.querySelector('input'), sugg = box.querySelector('.nav-sugg');
  var pfx = location.pathname.indexOf('/sectors/') > -1 ? '../' : '';
  var lib = [], rows = [], sel = -1;
  fetch(pfx + 'stockdata/index.json').then(function (r) { return r.json(); })
    .then(function (d) { lib = d || []; }).catch(function () {});
  function go(t) { location.href = pfx + 'stock.html#' + encodeURIComponent(t); }
  function close() { sugg.classList.remove('show'); sugg.innerHTML = ''; rows = []; sel = -1; }
  function paint() { [].forEach.call(sugg.querySelectorAll('.row'), function (r, i) { r.classList.toggle('sel', i === sel); }); }
  function search() {
    var v = input.value.trim().toUpperCase();
    if (!v) { close(); return; }
    rows = lib.filter(function (x) { return x.t.toUpperCase().indexOf(v) > -1 || (x.n || '').toUpperCase().indexOf(v) > -1; }).slice(0, 8);
    sel = -1;
    if (!rows.length) { sugg.innerHTML = '<div class="empty">No match in the nightly library.</div>'; sugg.classList.add('show'); return; }
    sugg.innerHTML = rows.map(function (x, i) {
      var st = (x.st || '').replace(/ /g, '_');
      return '<div class="row" data-i="' + i + '"><b>' + x.t + '</b><small>' + (x.n || '') + '</small>'
           + (x.st ? '<span class="stt st-' + st + '">' + x.st + '</span>' : '') + '</div>';
    }).join('');
    sugg.classList.add('show');
  }
  input.addEventListener('input', search);
  input.addEventListener('focus', function () { if (input.value.trim()) search(); });
  input.addEventListener('keydown', function (e) {
    if (!sugg.classList.contains('show')) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, rows.length - 1); paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); paint(); }
    else if (e.key === 'Enter') { e.preventDefault(); var pick = rows[sel] || rows[0]; if (pick) go(pick.t); }
    else if (e.key === 'Escape') { close(); input.blur(); }
  });
  sugg.addEventListener('mousedown', function (e) { var r = e.target.closest('.row'); if (!r) return; e.preventDefault(); go(rows[+r.dataset.i].t); });
  document.addEventListener('click', function (e) { if (!box.contains(e.target)) close(); });
}
```
And inside the `DOMContentLoaded` handler (alongside the legacy `.theme-btn`/`.lang-btn` wiring):
```js
document.querySelectorAll('.theme-switch').forEach(function (b) { b.addEventListener('click', window.toggleTheme); });
document.querySelectorAll('.lang-toggle .opt').forEach(function (o) { o.addEventListener('click', function () { setLang(o.getAttribute('data-l')); }); });
initNavSearch();
```
