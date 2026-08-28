# XPV2-SC-R3B — Hash / Deep-Link Evidence (commission §21 deliverable 9)

Candidate under test: `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`
(`BUILD_MANIFEST.json` output sha256 `0812bf7f…8610b5ce2`, 5,454,404 bytes).
Router under test: the verbatim embedded `si_workspace.js` (routing contract:
`research/reference_integrity/mastermind-xpv2-sector-r3/routing_contract.md`).

## Method

- `python3 -m http.server 8931` serving `proposal/`, Chromium (playwright-core
  1.62.1, Chrome for Testing 151.0.7922.34 at `chromium-1234`) headless.
- **One fresh browser context per landing** (31 landings total: 6 canonical +
  21 legacy anchors + `#read-gold_miners` + `#theme-gold_miners` + empty hash +
  one unknown hash). Viewport 1440×1000, `deviceScaleFactor:1`, dark/en
  (defaults — no drawer interaction for this pass).
- Each landing: `page.goto(BASE + hash, {waitUntil:'load'})`, then a 500ms
  settle wait (covers the shim's own 350ms `rescrollSettle()` timer,
  `runtime_shim.js` §5/F-6) before reading measurements.
- **Target-found / landing measurement**: for the 21 legacy anchors, the
  target element's `getBoundingClientRect().top` (viewport-relative, post
  any scroll) minus the sticky topbar's `getBoundingClientRect().bottom`
  (`.si-topbar`, measured 40px in every landing — a page-wide constant at
  this viewport). A landing that put the target directly under the sticky
  chrome reads ~15–17px; a larger residual names a seam, not a fail.
- **Recorder excerpt**: `window.REF.log` entries (`{seq,type,path,result}`)
  captured after each landing settles.
- Raw JSON backing this table: gathered live, not committed (evidence is the
  table below plus the screenshots this doc cross-references).

## 1. Six canonical hashes — target=null, never scroll (routing_contract §1)

| hash | resolved view | target scroll? | scrollY | notes |
|---|---|---|---|---|
| `#overview` | overview | none | 0 | as spec |
| `#map` | map | none | 0 | as spec |
| `#moving` | moving | none | 0 | as spec |
| `#money` | money | none | 0 | as spec |
| `#explore` | explore | none | 0 | as spec |
| `#confluence` | confluence | none | 0 | as spec — see §4 footnote |

All six resolve via `si_workspace.js`'s canonical-hash branch
(`VIEWS.indexOf(h)>=0`), which returns *before* the legacy-anchor lookup —
confirmed by `scrollY:0` on every one (no `scrollIntoView` call fires).

## 2. Twenty-one legacy anchors

Format: `top − stickyBottom` is the landing gap in CSS px. ~15–17px is a
clean landing (target sits just under the sticky chrome). A large residual
is the documented F-6 "hard ceiling" seam (see below the table), not a
routing failure — `activate()` itself always resolves the correct VIEW
regardless of the residual.

| hash | → view | target id | found | gap (top − 40) | scrollY | seam? |
|---|---|---|---|---|---|---|
| `#actnow-section` | overview | `actnow-section` | yes | 15.8px | 427 | clean |
| `#regime` | overview | `regime` | yes | 16.5px | 218 | clean |
| `#grader` | overview | `grader` | yes | **696.6px** | 452 | **F-6 hard ceiling** |
| `#si-map` | map | `si-map` | yes | 15.6px | 253 | clean |
| `#rotmap-section` | map | `rotmap-section` | yes | 15.6px | 201 | clean |
| `#sc-cyclemap` | map | `sc-cyclemap` | yes | 16.4px | 1652 | clean |
| `#board` | map | `board` | yes | 17.2px | 2754 | clean |
| `#si-movement` | moving | `si-movement` | yes | 15.6px | 201 | clean |
| `#rc-events-mount` | moving | `rc-events-mount` | yes | 15.9px | 239 | clean |
| `#rotation-app` | moving | `rotation-app` | yes | 15.5px | 1493 | clean |
| `#si-money` | money | `si-money` | yes | 15.6px | 189 | clean |
| `#internals-section` | money | `internals-section` | yes | 15.6px | 189 | clean |
| `#scc-leadership` | money | `scc-leadership` | yes | **179.9px** | 2011 | residual gap (see below) |
| `#explore-section` | explore | `explore-section` | yes | 15.6px | 189 | clean |
| `#table-section` | explore | `table-section` | yes | 15.6px | 189 | clean |
| `#chart-section` | explore | `chart-section` | yes | 16.4px | 1634 | clean |
| `#forming-narratives` | explore | `forming-narratives` | yes | 16.3px | 2510 | clean — see note |
| `#tm-mount` | explore | `tm-mount` | yes | **806.4px** | 2613 | **F-6 hard ceiling** |
| `#sc-app` | confluence | `sc-app` | yes | 16.5px | 271 | clean |
| `#sc-top` | confluence | `sc-top` | **no** | — | 0 | **recorded seam (c)** — target-not-found, view still correct |
| `#confluence` (as legacy) | confluence | `si-confluence` | yes | 83.3px | 0 | **shadowed/unreachable** — see §4 footnote |

### Notable seams (all pre-documented, none newly introduced)

- **`#sc-top` — target not found.** `document.getElementById('sc-top')` is
  `null` in this candidate; `activate()` swallows this silently and
  rewrites the hash to `#confluence` via `history.replaceState` (confirmed:
  `finalHash` after landing = `#confluence`, not `#sc-top`). This is
  routing_contract.md §8(c) reproducing exactly as documented: the VIEW
  still resolves correctly, only the intra-view scroll no-ops. `sc-top` as
  a *class* does exist (`<div class="r3-uni sc-top" id="cf-uni">`), just not
  as the literal id the legacy table names.
- **`#grader` and `#tm-mount` — F-6 hard-ceiling residual.** Both land with
  a large gap (696.6px, 806.4px) even after the 350ms rescroll-settle timer
  fires. This is the shim's own documented, *accepted* limitation
  (`build/runtime_shim.js` §5/F-6 comment, naming these exact two ids):
  the target sits close enough to the bottom of its view that
  `document.body.scrollHeight - window.innerHeight` is a hard ceiling —
  there is no more page below to scroll the target further up. Re-issuing
  `scrollIntoView` cannot fix a content-length property of the page. Not a
  new finding; reproduces the documented behavior.
- **`#scc-leadership` — 179.9px residual, same class as F-6, not previously
  named.** Index Leadership sits near the bottom of the Money view; the
  gap pattern matches F-6 (a target close to the page's scroll ceiling)
  though the shim's own comment names only `#grader`/`#tm-mount` as
  confirmed instances. Recorded here as an additional observed instance of
  the same documented seam class, not a new bug.
- **`#forming-narratives` — lands CLEAN (16.3px), contrary to the commission
  brief's framing of it alongside `#sc-top` as a "scroll no-op."** In this
  candidate the target `<section id="forming-narratives">` is a real,
  always-present top-level element (not nested inside an unopened partial —
  routing_contract.md's GAP #1 caveat was about the *production* template,
  `_forming_narratives.html.j2`, not this reference build). Measured
  landing is clean; reporting the actual measurement rather than the
  expected framing, per the frozen-spec instruction to report honestly.

## 3. `#read-gold_miners` (deliverable 9 + screenshot)

Lands on Overview (`activeView:overview`), `scrollY:615`. The Act-Now board
is populated asynchronously (`REF.fetchJSON('basketdata/baskets.json')` →
`window.__siViewReads()` → `reads()` → `openTrace('gold_miners')` retried
once the board exists), so this is a genuinely async landing, not an
instant one. Confirmed via direct DOM check: `#actnow .si-trace` exists,
`.si-trace-nm` reads "Gold Miners", the row's `aria-expanded="true"`.

**Screenshot: `read-trace-open.png`** — `#actnow` element crop showing the
Gold Miners row expanded into its trace card (Cycle: Prime entry ·
Conviction: 75 Accumulate · Confluence: 3/3 · Cycle Position: 22/100 ·
`members →`), the "AI Agents & Applications" / "Non-AI Software" rows still
collapsed below it, and "1 more here — sign in to see the full lane" (gated
preview, 3-of-4 shown) at the foot.

## 4. `#theme-gold_miners` (boot-only redirect, no navigation)

Confirmed via full `REF.log`:

```
#1 [boot ] basketdata/baskets.json — hit (sync boot parse)
#2 [nav  ] basket/gold_miners.html — recorded (would navigate to basket/gold_miners.html)
```

`location.href` after landing stays `…MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html#theme-gold_miners`
— no real navigation occurred, exactly as `REF.nav()`'s recorder contract
requires. `activeView` stays `overview` throughout (the resolver never
touches the router's own view state — routing_contract.md §3). This
reproduces `resolveThemeHash()`'s boot-only, `location.replace`-style
(recorded, not real) redirect faithfully.

**Footnote on `#confluence` as a legacy-table key**: `LEGACY_ANCHORS`
(`si_workspace.js`) contains an entry `'confluence':['confluence','si-confluence']`,
but `route()`'s canonical-hash check (`VIEWS.indexOf(h)>=0`) runs *before*
the legacy lookup and returns early — so this legacy entry is unreachable
for the literal string `#confluence` (it would only ever fire for a hash
that reached the legacy branch some other way, which none does). Measuring
`si-confluence`'s natural position anyway (83.3px below the sticky bar,
`scrollY:0`, no scroll performed) confirms the canonical path won: had the
legacy scroll fired, `scrollY` would be nonzero.

## 5. Empty hash

Landing: `activeView:overview`, `finalHash` **rewritten to `#overview`** via
`history.replaceState` — matches `si_workspace.js:317-318`'s
`if(!h&&history.replaceState) history.replaceState(null,'','#overview')`.

## 6. Unknown hash (`#does-not-exist-zzz`)

Landing: `activeView:overview` (unknown → overview, `activate()`'s own
defensive re-clamp), **`finalHash` stays `#does-not-exist-zzz`** — NOT
rewritten. This is correct per §5 of the routing contract: the URL-rewrite
branch is gated on `!h` (empty hash only); an unrecognized *non-empty* hash
lands on Overview but is left in the address bar untouched. Confirmed
against the literal source: the rewrite line runs unconditionally after
`activate('overview',null)` but its own `if(!h …)` guard is false here.

## Cross-reference

Every canonical/legacy/read/theme/empty/unknown landing above also
underlies the six-view PRIMARY screenshot set (`overview-1440-dark-en.png`
etc., loaded via `#<view>`) and `read-trace-open.png`. No other landings in
this document required their own screenshot per the commission (§21
deliverable 9 asks for the measurement table; the one screenshot obligation
was `#read-gold_miners` → `read-trace-open.png`, satisfied above).
