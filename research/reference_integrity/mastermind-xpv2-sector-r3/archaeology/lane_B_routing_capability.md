# Lane B — Sector Central (US) Routing & Capability Contract
XPV2-SC-R3A, sub-lane B. Reconstructed 2026-08-20 from production code at the
worktree's checked-out HEAD. Authority order: production code first; the R2
critic packet (`research/reference_integrity/mastermind-xpv2-turn3-r2/reviews/product_regression.md`)
is treated as a lead and checked against code, never as truth on its own.

Router source of truth: `templates/si_workspace.js` (328 lines), an external script
loaded by `templates/sector_central.html.j2:3532` (`<script src="si_workspace.js">`).
It is a *separate* IIFE from the page's inline script — the inline script's own
functions (`boot()`, `resolveThemeHash()`) cannot see the router's internals and
vice versa (comment, `sector_central.html.j2:3081-3086`). Confirmed present
identically in the rendered `site/si_workspace.js` (not re-diffed line-by-line;
same file, checked in alongside the template — see GAPS).

## 1. The six canonical views and their identifiers

`templates/si_workspace.js:17`
```js
var VIEWS=['overview','map','moving','money','explore','confluence'];
```
Titles (`si_workspace.js:18-20`):
- `overview` → EN "Overview" / ZH "总览"
- `map` → "The Map" / "全景图谱"
- `moving` → "What's Moving" / "正在轮动"
- `money` → "Money & Breadth" / "资金与广度"
- `explore` → "Explore" / "深入探索"
- `confluence` → "Confluence" / "子行业汇聚"

Rail buttons (real anchor elements, canonical hash form) —
`templates/sector_central.html.j2:1686-1696`:
```html
<a class="si-view-btn on" data-view="overview" href="#overview" aria-current="page">…Overview…</a>
<a class="si-view-btn" data-view="map" href="#map">…The Map…</a>
<a class="si-view-btn" data-view="moving" href="#moving">…What's Moving…</a>
<a class="si-view-btn" data-view="money" href="#money">…Money & Breadth…</a>
<a class="si-view-btn" data-view="explore" href="#explore">…Explore…</a>
<a class="si-view-btn" data-view="confluence" href="#confluence">…Confluence…</a>
```
Each view is a `<section class="si-view" data-view="…">` in the DOM; exactly one
carries class `.on` at a time (comment `sector_central.html.j2:1670-1674`; CSS rule
`.si-view{display:none} .si-view.on{display:block}` — `sector_central.html.j2:1156-1157`).
Section boundaries in the template (file:line, open→close):
- overview: `sector_central.html.j2:1709` → `:2257`
- map: `:2259` → `:2369`
- moving: `:2371` → `:2386`
- money: `:2388` → `:2422`
- explore: `:2424` → `:2476`
- confluence: `:2478` → `:2515` (id `si-confluence`)

The confluence view has no `.si-view-read` slot — its own hero (`.sc-top` /
`.sc-lede`) is its read (comment, `si_workspace.js:12-16`).

## 2. Every canonical hash the router accepts

Exactly the six `VIEWS` strings above, matched verbatim (no aliasing, no
case-folding) at `si_workspace.js:315`:
```js
if(VIEWS.indexOf(h)>=0){ activate(h,null); return; }
```
`h` is `location.hash` with the leading `#` stripped and `decodeURIComponent`-ed
(`si_workspace.js:311-312`). So the six accepted canonical hashes are exactly
`#overview #map #moving #money #explore #confluence`.

## 3. Every LEGACY hash and what it maps to

`LEGACY_ANCHORS` — verbatim, `si_workspace.js:40-64`:
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
That is **21 legacy anchors**, each mapping `[view, intra-view scroll target id]`.
Dispatch: `si_workspace.js:316`:
```js
if(LEGACY_ANCHORS[h]){ activate(LEGACY_ANCHORS[h][0],LEGACY_ANCHORS[h][1]); return; }
```
`activate(view,target)` switches to `view` (per §1) and then, if `target` is
given, scrolls the element with that id into view — see §7.

The ids on the right of each pair are the ORIGINAL pre-V2 section ids, preserved
byte-intact inside the wrapped `.si-view` sections specifically so this table can
still reach them (comment, `si_workspace.js:33-37`; render-mode-preservation
comment `sector_central.html.j2:1672-1674`). This table is pinned by
`tests/test_si_workspace_shell.py` per the in-code comment at `si_workspace.js:37`
(not independently re-opened in this census — see GAPS).

Verified target-id existence in the template (static ids; three of the 21 are
generated at runtime and are not literal template ids — see below):
- `actnow-section` → `sector_central.html.j2:2201`
- `regime` → `:2178`
- `grader` → `:2206`
- `si-map` → `:2263`
- `rotmap-section` → `:2262`
- `sc-cyclemap` → `:2306`
- `board` → `:2364`
- `si-movement` → `:2374`
- `rc-events-mount` → `:2381`
- `rotation-app` → `:2382`
- `si-money` → `:2390`
- `internals-section` → `:2391`
- `scc-leadership` → `:2419`
- `explore-section` → `:2427`
- `table-section` → `:2432`
- `chart-section` → `:2445`
- `tm-mount` → `:2463`
- `si-confluence` → `:2478` (target id `si-confluence` matches the `confluence` legacy key's target)
- `sc-app` → `:2505`
- `forming-narratives` — NOT a literal id in `sector_central.html.j2`; it is
  pulled in via `{% include "_forming_narratives.html.j2" %}` at `:2465`, so its
  target element (if any) lives in that included partial (not opened in this
  census — GAP).
- `sc-top` — NOT a literal id in `sector_central.html.j2` (a `<div class="sc-top">`
  exists at `:2490` but has no `id="sc-top"`); the legacy map still routes to the
  `confluence` view (target search simply fails silently if the id is absent —
  `activate()` falls back to a hash `replaceState`, see §7). This is a genuine
  code-vs-code loose end worth flagging to R3, not a critic claim to adjudicate
  here (OUT OF SCOPE per commission — routing/hash surface only).

**Refutation of the R2 critic's specific completeness claim:** PRC-003
(`research/reference_integrity/mastermind-xpv2-turn3-r2/reviews/product_regression.md:43-52`)
asserts the router "collapses legacy hashes … including `si-map`, `rotation-app`,
`sc-app`, and `sc-top`" and cites `si_workspace.js:32-64,310-318` — those line
numbers match this census's read almost exactly (§ headers at :32 vs :32-64
above land the same table). All four hashes it names (`si-map`, `rotation-app`,
`sc-app`, `sc-top`) ARE present as keys in `LEGACY_ANCHORS` (verbatim table
above) and DO map to a view. The critic's claim is about a **candidate/mockup**
under review, not about this production router — read literally, "the router …
collapses" is ambiguous about which router (candidate vs production); against
production code the four named hashes are NOT dropped. This census cannot
adjudicate what the R2 candidate itself did (out of scope — no candidate file
was supplied in-scope to Lane B); it only confirms production's own table is
intact and matches the critic's own line-number citation of production.

## 4. The `#theme-*` hash family

Handling is split across the router (which explicitly refuses to touch it) and
a separate inline-script function that owns it.

Router refusal — `si_workspace.js:313`:
```js
if(h.indexOf('theme-')===0){ activate('overview',null); return; }  // resolver owns it
```
So on `hashchange`, a `#theme-<id>` hash routes the six-view rail to `overview`
(display only) and does nothing else — see the gap below.

Owner — `resolveThemeHash()`, `templates/sector_central.html.j2:2813-2818`:
```js
function resolveThemeHash(){
  let id=location.hash.slice(7);          // '#theme-'.length
  try{ id=decodeURIComponent(id); }catch(e){}
  if(!id||!themeById(id)) return;         // unknown id → stay put rather than 404
  location.replace('basket/'+encodeURIComponent(id)+'.html');
}
```
It is invoked from `boot()` **once, at initial page load only**:
`sector_central.html.j2:3069`:
```js
if(location.hash.startsWith('#theme-')) resolveThemeHash();
```
`boot()` runs once (`sector_central.html.j2:3079: boot();`) and there is no
`hashchange` listener anywhere in `sector_central.html.j2` that calls
`resolveThemeHash()` again (confirmed by exhaustive grep — the only two hits for
`resolveThemeHash`/`hashchange` in that file are the definition at `:2813` and the
one boot-time call at `:3069`). `location.replace()` (not `.href=`) is used
deliberately so the redirect does not enter browser history — Back returns to
whatever sent the visitor to `#theme-<id>`, not back through the hash bounce
(comment, `:2809-2812`, citing prior decisions #4254/#4237). An unknown theme id
is a silent no-op (stays on the page, on Overview).

**GAP / real behavioral seam (not a critic claim, code-vs-code observation):**
because the router's own `hashchange` listener (`si_workspace.js:323`,
`window.addEventListener('hashchange',route)`) intercepts `#theme-*` first and
just activates Overview, a `#theme-<id>` hash arriving via an **in-page** hash
change (e.g. an app-internal link clicked after first load, not a fresh
navigation) does NOT reach `resolveThemeHash()` and will NOT redirect to the
basket page — it only lands on Overview. Only the very first hash present at
initial document load triggers the actual basket-page redirect. This is a
genuine mechanism to carry into R3's contract, since a redesign that "reuses"
this router verbatim inherits the same seam.

## 5. The `#read-*` trace hash family

`si_workspace.js:314`:
```js
if(h.indexOf('read-')===0){ pendingTrace=h.slice(5); activate('overview',null); return; }
```
Behavior: always activates `overview` (the Act-Now lane board lives only there),
and stores the id after `read-` (e.g. `#read-XYZ` → `pendingTrace='XYZ'`).
`activate()` calls `reads()` (`si_workspace.js:303`), and `reads()`'s last line
(`si_workspace.js:255`) is:
```js
if(pendingTrace) openTrace(pendingTrace);
```
`openTrace(id)` (`si_workspace.js:260-268`):
```js
function openTrace(id){
  var lanes=document.getElementById('actnow'); if(!lanes||!window.__siTrace) return;
  var row=null, rows=lanes.querySelectorAll('.rvx-trow[data-mlc-bid]');
  for(var i=0;i<rows.length;i++){ if(rows[i].getAttribute('data-mlc-bid')===id){ row=rows[i]; break; } }
  if(!row) return;
  pendingTrace=null;
  row.click();
  try{ row.scrollIntoView({block:'center'}); }catch(e){ row.scrollIntoView(); }
}
```
- If the Act-Now board (`#actnow`, injected asynchronously by `_us_act_now_board.html.j2`
  content fetched into it — `sector_central.html.j2:3601-3607`) is not yet
  populated, `openTrace` returns silently and `pendingTrace` is left set (it is
  ONLY cleared once a matching row is found — line 265 runs after the `if(!row)
  return`). It is retried the next time `reads()` runs, which happens again once
  the payload fetch resolves and calls `window.__siViewReads(BASKETS)`
  (`sector_central.html.j2:3088`) — comment at `si_workspace.js:258-259`
  confirms this is deliberate ("held until it exists").
- If `id` never matches any row (`data-mlc-bid`), the trace silently never opens
  and `pendingTrace` stays set forever (harmless — it is just re-tried on every
  future `reads()` call, e.g. a language toggle).
- `row.click()` triggers whatever click handler the Act-Now board wires (not
  re-opened in this census; out of scope — it belongs to the lane/board
  producer, not the routing contract). `scrollIntoView({block:'center'})` has no
  explicit `behavior`, so it defaults to `'auto'` (instant), not `'smooth'` — the
  smooth-scroll no-op trap does not apply to this call as written.

## 6. Unknown-hash behavior

`si_workspace.js:317-318`:
```js
activate('overview',null);                                        // unknown → overview
if(!h&&history.replaceState) history.replaceState(null,'','#overview');
```
Falls through from the `#theme-`, `#read-`, canonical-view, and legacy-anchor
checks (§2-5) — any hash matching none of those four rules lands on Overview
with no error state, no console warning, and no scroll target. `activate()`
itself also defensively re-clamps (`si_workspace.js:274`):
```js
if(VIEWS.indexOf(view)<0) view='overview';
```
so even a malformed call path cannot activate a non-existent view. Additionally,
if the hash is EMPTY (e.g. bare `sector_central.html` with no `#` at all), the
router still activates Overview and then rewrites the URL to `#overview` via
`history.replaceState` (no navigation, no reload) — this only fires when `h` is
falsy, i.e. exactly the empty-hash case, not other unknown hashes.

## 7. Deep-link scroll behavior & sticky-header interaction

`activate(view,target)`, `si_workspace.js:304-308`:
```js
if(target){
  var el=document.getElementById(target);
  if(el){ try{ el.scrollIntoView({block:'start'}); }catch(e){ el.scrollIntoView(); } }
  else if(history.replaceState) history.replaceState(null,'','#'+view);
}
```
- Only fires when a legacy anchor supplied a scroll target (canonical `#view`
  hashes pass `target=null` and never scroll — landing at the top of the newly
  shown view is the only "scroll" that happens, via the view's own `display:none`
  → `display:block` toggle).
- `scrollIntoView({block:'start'})` — no `behavior` key, so it defaults to
  `'auto'` (instant jump), NOT `'smooth'`. Per the KNOWN TRAP in the commission,
  a critic seeing "no scroll" in the Browser-pane automation context for a
  `behavior:'smooth'` call would be looking at a pane artifact — but this
  production code does not even specify `'smooth'`, so that trap does not apply
  here; any critic-reported scroll failure on THIS mechanism is not explained by
  the automation-pane smooth-scroll no-op and would need a different cause (not
  investigated further — out of scope, R2 mockup's candidate code may differ).
- If the target id does not exist in the DOM (e.g. `sc-top`, per §3's gap),
  `activate()` silently swallows it and instead rewrites the hash to the bare
  view hash via `history.replaceState` — no error, no scroll, no fallback
  scroll-to-view-top forced (the view is already showing from the `.on` class
  toggle earlier in `activate()`, so visually it looks like "landed at top of
  view").
- **No sticky-header offset compensation exists.** The workspace's own sticky
  element is `.si-side` (`sector_central.html.j2:1137`: `position:sticky; top:0;
  height:100vh`), a LEFT-column rail, not a top bar, on desktop and the
  ≤1100px tier — it does not overlay vertically scrolled content, so no
  `scroll-margin-top` compensation is needed or present for it. On mobile
  (`@media (max-width:767px)`, `sector_central.html.j2:1187-1198`), `.si-side`
  becomes `position:sticky; top:0` as a horizontal TOP tab bar
  (`:1189-1191`) — this genuinely does overlay the top of scrolled content, and
  NONE of the legacy-anchor target elements carry `scroll-margin-top` to
  compensate (grep of `scroll-margin-top` in the template hits only
  `.detail`/`.rvx-lane-desc`-adjacent card classes at `:131` and `:155`, unrelated
  to the legacy-anchor target ids). This is a genuine (small) mobile deep-link
  gap in the production mechanism — noted for R3, not something R2 flagged.
- Timing: `activate()` mounts lazy organs synchronously via a forced
  `offsetHeight` reflow (comment `si_workspace.js:284-290`) specifically so the
  scroll-into-view / width-measuring organs do not race a `requestAnimationFrame`
  that never fires in a background tab. The scroll call itself (`:306`) runs
  synchronously right after that reflow, in the same `activate()` call, so no
  additional delay/timeout gates the scroll.
- No scroll position is otherwise "restored" per view — switching views via the
  rail buttons does not remember or reapply a prior scroll offset; each
  activation either scrolls to a legacy target or leaves the viewport wherever
  it already was (typically the top, since the newly `.on` section starts fresh
  in flow).

## 8. Working-destination inventory per view

Distinguishing **static template hrefs** (verbatim strings) from **runtime-
generated hrefs** (JS template-string patterns, cited by generator function +
file:line since the concrete href depends on nightly data).

### Overview (`sector_central.html.j2:1709-2257`)
Static:
- `sector_central.html.j2:2163` — `<a class="rvx-chip" href="allocation.html">Open the playbook →</a>`
- `sector_central.html.j2:2205` — `<a href="#confluence">Drill to stocks →</a>` (in-page view switch, not a page nav)
- `_us_act_now_board.html.j2:31` — `<a href="plans.html">sign in to see the full lane</a>` (tier gate, gated content)
- `_us_act_now_board.html.j2:297,565,584,603,622,646` — `<a href="sector_central.html#actnow-section">…full list on Sector Intelligence →</a>` (self-referential legacy anchor, 6 occurrences)
Runtime-generated (Act-Now lane items):
- `_us_act_now_board.html.j2:459,482` — `<a class="actitem" data-rpop href="{{ x.href }}">` — data-driven destination href supplied per lane item by the board's own producer (not re-opened; belongs to lane content, out of scope)
- Day-tape-pulse mover rows, mounted inside Overview at `sector_central.html.j2:1743` (`#ftr-dtp-body`): `sector_central.html.j2:1909` — `return '<a class="dtp-mrow" href="basket/'+esc(b.id)+'.html">'…` — one link per top/bottom mover, target `basket/<id>.html`.
- Act-Now trace-expand rows carry `data-mlc-bid` and open via click/`__siTrace`, with a same-basket fallback: `sector_central.html.j2:3108`: `location.href=row.getAttribute('href')` if no trace HTML is available.
Count: 2 fully-static page hrefs + 1 gated (`plans.html`) + 6 duplicated self-anchors + 2 data-driven patterns (act-items, movers).

### Map (`sector_central.html.j2:2259-2369`)
Runtime-generated:
- `sector_central.html.j2:3009` — `renderRotBoard()`: `return '<a class="rvx-brow" href="basket/'+encodeURIComponent(d.id)+'.html" …'` — one row per rotation-board theme, target `basket/<id>.html`.
No static hrefs found inside the map section body itself (the section's other content is chart/canvas rendering, not opened further — out of scope).
Count: 1 data-driven pattern (rotation board rows, N per nightly payload).

### Moving (`sector_central.html.j2:2371-2386`)
Contains only three mount points (`#rc-events-mount`, `#rotation-app`, `#desk-watch-mount`) populated by lazily-injected scripts `rotation_events.js`, `subsector_rotation.js`, `desk_watch.js` (LAZY map, `si_workspace.js:78`). No hrefs are literal in `sector_central.html.j2` for this view; their content is out of scope (owned by those scripts, not the routing contract) — flagged as GAP below rather than asserted empty.
Count: 0 hrefs directly verified in this file; destination surface lives in 3 deferred scripts not opened.

### Money (`sector_central.html.j2:2388-2422`)
No literal `<a href>` found in the money section body in `sector_central.html.j2` (verified by the same href grep restricted to this line range — none present). Its content (`#heatmap-scorecard`, `#scc-leadership`) is populated by lazily-injected `heatmap.js` and shared leadership-render code:
- `heatmap.js:540-541` — gated tease link: `<a href="plans.html">See plans</a>`
- `heatmap.js:1366,1611` — `'<a class="hm-mrow" href="' + STOCK_URL + encodeURIComponent(t.t) + '">'` where `STOCK_URL = data.stock_url || 'stock.html#'` (`heatmap.js:826`) — per-stock destination, pattern `stock.html#<TICKER>`.
Count: 1 gated static (`plans.html`, inside heatmap.js) + 1 data-driven per-stock pattern (`stock.html#<ticker>`).

### Explore (`sector_central.html.j2:2424-2476`)
Static:
- `sector_central.html.j2:2698` — click handler (not a literal href, a JS navigation): `n.onclick=()=>{ const id=n.dataset.id||''; if(/^[a-z0-9_-]+$/i.test(id)) location.href='basket/'+id+'.html'; });` — clicking a basket-table name row navigates to `basket/<id>.html`.
- `_forming_narratives.html.j2` (included at `:2465`) not opened in this census — its content, if any hrefs, is a GAP (see below).
Runtime:
- Time Machine mount (`#tm-mount`, `:2463`) is populated by lazily-injected `time_machine.js` — not opened, GAP.
Count: 1 verified data-driven navigation (basket table row click → `basket/<id>.html`) + 2 unopened mounts (forming-narratives include, time_machine.js).

### Confluence (`sector_central.html.j2:2478-2515`)
Static:
- `sector_central.html.j2:2511` — `<a href="#moving">See the rotation map</a>` (in-page view switch)
Runtime (via lazily-injected `subsectors.js`, mounted on first `#confluence` open per `LAZY.confluence=['subsectors.js']`, `si_workspace.js:85`):
- `subsectors.js:65` — `function detailHref(ds, key) { var d = DS[ds]; return d.dir + d.prefix + key + '.html'; }` — subsector detail page href, composed from a per-dataset dir/prefix.
- `subsectors.js:66` — `function stockHref(tk) { return 'stock.html#' + encodeURIComponent(tk); }` — per-stock destination, pattern `stock.html#<TICKER>`.
- `subsectors.js:204,280,325,327,401,485` — six call sites wiring `nm`/`gcard`/table-row anchors through `detailHref`/`stockHref` (or `'#'` fallback at `:485` when `g.chart_key` is falsy — a genuine intentional non-destination for unscored rows, not a stray placeholder).
Count: 1 static in-page switch + 2 data-driven href-generator functions used across 6 render call sites (subsector detail pages + per-stock pages), plus one conditional `#` fallback for unscored rows.

## Summary table — canonical + legacy hash surface

| Family | Count | Behavior |
|---|---|---|
| Canonical view hashes | 6 (`#overview #map #moving #money #explore #confluence`) | exact match → `activate(view,null)` |
| Legacy anchor hashes | 21 (`LEGACY_ANCHORS`) | → `activate(view, targetId)`, scrolls to `targetId` if it exists in DOM |
| `#theme-<id>` | handled OUTSIDE the router by `resolveThemeHash()`, boot-time only | router itself just shows Overview; only the very first page-load hash triggers the real `location.replace()` redirect to `basket/<id>.html` |
| `#read-<id>` | 1 pattern | shows Overview, opens (or defers, or silently never opens) the Act-Now trace row matching `data-mlc-bid===<id>` |
| unknown/empty | fallback | shows Overview; empty hash additionally rewrites URL to `#overview` via `replaceState` |

## GAPS

1. `_forming_narratives.html.j2` and `time_machine.js` (Explore view mounts) not
   opened — their internal destination surface is unverified. Coverage: their
   inclusion point and mount id are confirmed (`sector_central.html.j2:2463,2465`);
   contents are not.
2. `rotation_events.js`, `subsector_rotation.js`, `desk_watch.js` (Moving view's
   three lazy mounts) not opened — the Moving view has 0 verified literal hrefs
   in the template itself; its real destination surface is unverified and may be
   non-trivial (these scripts render the rotation map/board content per the
   `LAZY.moving` list, `si_workspace.js:78`).
3. `tests/test_si_workspace_shell.py` (cited in-code as the pin for
   `LEGACY_ANCHORS`) was not opened to independently confirm the table is truly
   under CI lock — taken on the in-code comment's word (`si_workspace.js:37`).
4. `site/sector_central.html` (rendered output) and `site/si_workspace.js` exist
   on disk in this worktree (not sparse-omitted; both were listed by the initial
   `wc -l`), but this census did not byte-diff them against the templates to
   confirm the render is current — the routing contract above is sourced from
   the TEMPLATE (production source), per the commission's authority order.
5. `data-tip-t-en`/tier-gating logic for which destinations are auth-tier-gated
   was NOT systematically enumerated beyond the two confirmed `plans.html`
   tease links (Overview act-now-lane overflow, Money-view heatmap stock rows)
   — a full auth-tier gating map of every destination was not built (out of
   scope per the commission's field-authority carve-out to lanes A/C/D/E, but
   flagged since Q7 of the commission asks specifically "which destinations are
   conditional on auth tier").
6. The R2 critic packet's remaining routing-adjacent claims (PRC list items
   beyond PRC-003, e.g. `href="#"` placeholders, method-route/LENS claims) were
   not individually re-verified against a specific R2 CANDIDATE file — no
   candidate template was in scope for Lane B (SCOPE lists only production
   files); PRC-003 was checked because it is the one claim that names production
   line ranges directly comparable to what this census read.

## DEVIATIONS

None — worked within SCOPE (`templates/sector_central.html.j2`, the router it
defers to `templates/si_workspace.js`, `templates/nav_market.js`/`theme.js` were
checked and found NOT to contain router logic, and the R2 critic evidence file).
No production edits made.
