# XPV2-SC-R3A — Routing Contract (Deliverable 4)

Source: `archaeology/lane_B_routing_capability.md`. Frozen ruling: `ADJUDICATIONS.md` §A7.
Router source of truth: `templates/si_workspace.js` (328 lines), loaded by
`templates/sector_central.html.j2:3532`. **R3 MUST reuse `templates/si_workspace.js`
verbatim, including `resolveThemeHash()` (owned by the inline script at
`sector_central.html.j2:2813-2818`) — it must NOT be reimplemented.** A
redesign that reuses this router inherits every mechanism and every seam
documented below.

## 1. The six canonical views

`templates/si_workspace.js:17`:
```js
var VIEWS=['overview','map','moving','money','explore','confluence'];
```

| view id | EN title | ZH title |
|---|---|---|
| `overview` | Overview | 总览 |
| `map` | The Map | 全景图谱 |
| `moving` | What's Moving | 正在轮动 |
| `money` | Money & Breadth | 资金与广度 |
| `explore` | Explore | 深入探索 |
| `confluence` | Confluence | 子行业汇聚 |

Exactly one `<section class="si-view" data-view="…">` carries `.on` at a
time (`.si-view{display:none} .si-view.on{display:block}`). Confluence has
NO `.si-view-read` slot — its own hero (`.sc-top`/`.sc-lede`) is its read
(`si_workspace.js:12-16`).

Canonical hashes accepted (exact match, no aliasing, no case-folding,
`si_workspace.js:315`): `#overview #map #moving #money #explore #confluence`.

## 2. LEGACY_ANCHORS — verbatim, 21 entries

`si_workspace.js:40-64`:

```js
var LEGACY_ANCHORS={
  'actnow-section':['overview','actnow-section'],
  'regime':['overview','regime'],
  'grader':['overview','grader'],
  'si-map':['map','si-map'],
  'rotmap-section':['map','rotmap-section'],
  'sc-cyclemap':['map','sc-cyclemap'],
  'board':['map','board'],
  'si-movement':['moving','si-movement'],
  'rc-events-mount':['moving','rc-events-mount'],
  'rotation-app':['moving','rotation-app'],
  'si-money':['money','si-money'],
  'internals-section':['money','internals-section'],
  'scc-leadership':['money','scc-leadership'],
  'explore-section':['explore','explore-section'],
  'table-section':['explore','table-section'],
  'chart-section':['explore','chart-section'],
  'forming-narratives':['explore','forming-narratives'],
  'tm-mount':['explore','tm-mount'],
  'confluence':['confluence','si-confluence'],
  'sc-app':['confluence','sc-app'],
  'sc-top':['confluence','sc-top']
};
```

Each key maps `[view, intra-view scroll target id]`. Dispatch:
`si_workspace.js:316`: `if(LEGACY_ANCHORS[h]){ activate(LEGACY_ANCHORS[h][0],LEGACY_ANCHORS[h][1]); return; }`.
This table is pinned by `tests/test_si_workspace_shell.py` per the in-code
comment at `si_workspace.js:37` (not independently re-opened by lane B's
census — see GAPS).

**Refutation on record**: the R2 critic's PRC-003 claimed the router
"collapses legacy hashes … including `si-map`, `rotation-app`, `sc-app`, and
`sc-top`." All four ARE present as keys above and DO map to a view against
production code — the claim does not hold against production (it may
describe the R2 candidate, not audited here).

**Target-id existence caveat (code-vs-code, not repaired this wave):**
`forming-narratives`'s target lives inside the included partial
`_forming_narratives.html.j2`, not opened by this census (GAP). `sc-top`'s
target does NOT exist as a literal `id="sc-top"` in `sector_central.html.j2`
(only an unrelated `<div class="sc-top">` at `:2490`) — the legacy hash still
routes to the `confluence` view correctly, but the scroll-target lookup
fails silently (see §5, `activate()`'s target-not-found branch). This is
recorded seam (c) below.

## 3. The `#theme-<id>` hash family

Split across the router (which refuses to touch it) and a separate
inline-script function that owns it:

- Router refusal, `si_workspace.js:313`: `if(h.indexOf('theme-')===0){ activate('overview',null); return; }  // resolver owns it`
- Owner, `resolveThemeHash()` (`sector_central.html.j2:2813-2818`):
  ```js
  function resolveThemeHash(){
    let id=location.hash.slice(7);
    try{ id=decodeURIComponent(id); }catch(e){}
    if(!id||!themeById(id)) return;
    location.replace('basket/'+encodeURIComponent(id)+'.html');
  }
  ```
- Invoked from `boot()` **once, at initial page load only**
  (`sector_central.html.j2:3069`: `if(location.hash.startsWith('#theme-')) resolveThemeHash();`).
  `location.replace()` (not `.href=`) so the redirect does not enter browser
  history.

## 4. The `#read-<id>` trace hash family

`si_workspace.js:314`: `if(h.indexOf('read-')===0){ pendingTrace=h.slice(5); activate('overview',null); return; }`.
Always activates Overview (the Act-Now board lives only there) and stores the
id. `reads()`'s last line calls `openTrace(pendingTrace)` if set. `openTrace(id)`
(`si_workspace.js:260-268`) searches `#actnow .rvx-trow[data-mlc-bid=id]`; if
the board is not yet populated it returns silently and `pendingTrace` stays
set — retried on the NEXT `reads()` call (e.g. once the payload fetch
resolves, or a language toggle). An id that never matches any row leaves
`pendingTrace` set forever, harmlessly re-tried.

## 5. Unknown-hash and empty-hash behavior

`si_workspace.js:317-318`:
```js
activate('overview',null);                                        // unknown → overview
if(!h&&history.replaceState) history.replaceState(null,'','#overview');
```
Any hash matching none of canonical/legacy/`#theme-`/`#read-` lands on
Overview with no error state, no console warning, no scroll target.
`activate()` itself defensively re-clamps (`si_workspace.js:274`:
`if(VIEWS.indexOf(view)<0) view='overview';`). An EMPTY hash additionally
rewrites the URL to `#overview` via `history.replaceState` (no navigation, no
reload) — this only fires when `h` is falsy.

## 6. Deep-link scroll mechanics

`activate(view,target)` (`si_workspace.js:304-308`):
```js
if(target){
  var el=document.getElementById(target);
  if(el){ try{ el.scrollIntoView({block:'start'}); }catch(e){ el.scrollIntoView(); } }
  else if(history.replaceState) history.replaceState(null,'','#'+view);
}
```
- `scrollIntoView({block:'start'})` — **no `behavior` key**, defaults to
  `'auto'` (instant), NOT `'smooth'`. The known automation-pane
  smooth-scroll no-op trap does NOT apply to this call as written.
- Canonical `#view` hashes pass `target=null` and never scroll.
- If the target id does not exist in the DOM (§2's `sc-top` caveat),
  `activate()` silently swallows it and rewrites the hash to the bare view
  hash via `history.replaceState` — no error, no fallback scroll.
- No scroll position is otherwise "restored" per view.

## 7. Working-destination inventory per view

From lane B §8, distinguishing static template hrefs from runtime-generated
(JS template-string) hrefs:

| view | static hrefs | runtime-generated destinations |
|---|---|---|
| Overview | `allocation.html` (playbook), `#confluence` (in-page), `plans.html` (gated tease), `sector_central.html#actnow-section` ×6 (self-anchor) | act-item rows (`x.href`, data-driven), day-tape-pulse mover rows → `basket/<id>.html`, act-now trace-expand fallback `location.href=row.getAttribute('href')` |
| Map | none found in section body | rotation-board rows → `basket/<id>.html` (N per nightly payload) |
| Moving | none (0 verified literal hrefs in the template itself) | destination surface lives in 3 deferred/lazy scripts not opened this pass (GAP) |
| Money | none in section body | `plans.html` gated tease (inside `heatmap.js`); per-stock `stock.html#<TICKER>` pattern (`hm-mrow` rows) |
| Explore | JS click handler (not literal href) → `basket/<id>.html` on basket-table row click | Time Machine mount (not opened, GAP); `_forming_narratives.html.j2` include (not opened, GAP) |
| Confluence | `#moving` (in-page, "See the rotation map") | `detailHref(ds,key)` → `<dir><prefix><key>.html`; `stockHref(tk)` → `stock.html#<TICKER>`; conditional `#` fallback at `subsectors.js:485` for unscored rows (intentional non-destination, not a stray placeholder) |

## 8. Recorded seams — filed separately, NOT repaired this wave (ADJUDICATIONS §A7)

R3 must carry these forward as known behavior, not attempt to fix them:

- **(a)** `#theme-*` resolves only at initial boot, never on a later
  `hashchange` — because the router's own `hashchange` listener intercepts
  `#theme-*` first and just activates Overview (§3). An in-page hash change
  to `#theme-<id>` after first load does NOT redirect to the basket page.
- **(b)** Mobile ≤767px sticky top bar has no compensating
  `scroll-margin-top` on legacy anchor targets. `.si-side` becomes a
  horizontal top tab bar under `@media (max-width:767px)` and genuinely
  overlays scrolled content; no legacy-anchor target id carries
  `scroll-margin-top` to compensate.
- **(c)** `sc-top` and `forming-narratives` legacy anchor targets are not
  confirmed present as literal DOM ids (§2 caveat) — routing to the correct
  VIEW still works; only the intra-view scroll may silently no-op.

## GAPS carried forward from lane B

1. `_forming_narratives.html.j2` and `time_machine.js` (Explore mounts) not
   opened — destination surface unverified beyond mount id.
2. `rotation_events.js`, `subsector_rotation.js`, `desk_watch.js` (Moving's
   three lazy mounts) not opened — 0 verified literal hrefs in the template
   itself for this view.
3. `tests/test_si_workspace_shell.py` (cited as the LEGACY_ANCHORS pin) was
   not independently re-opened by lane B.
4. `site/sector_central.html`/`site/si_workspace.js` (rendered output) were
   not byte-diffed against the templates to confirm currency — this
   contract is sourced from the TEMPLATE (production source) per authority
   order.
5. A full auth-tier gating map of every destination was not built — only the
   two confirmed `plans.html` tease links are named.
6. R2 critic packet's remaining routing-adjacent claims beyond PRC-003 were
   not individually re-verified — no candidate template was in scope for
   lane B.
