# XPV2-SC-R3B production baseline — PROVENANCE

Captures the RIG V1 S4/S5 production-baseline evidence set for
`mastermind-xpv2-sector-r3b` (`research/reference_integrity/mastermind-xpv2-sector-r3b/baseline.yml`,
`evidence.screenshots`): the six canonical Sector Central views
(Overview / The Map / What's Moving / Money & Breadth / Explore / Confluence)
at desktop / dark / EN.

## Why a pinned-commit local render, not a live capture

A prior lane in this program established that the live site 401-gates every
non-Overview view asset for an anonymous visitor: `https://www.mastermind-x.com/sector_central.html`
returns `x-regwall: deny` on `si_workspace.js` and every view artifact, with
response body `{"locked":true,"reason":"authentication_required","signin_url":"/?signin=1"}`.
Signing in to capture the gated views is prohibited by this commission's
SCOPE. Live anonymous capture of Map/Moving/Money/Explore/Confluence is
therefore impossible without violating that prohibition.

The committed `site/` tree in this repository IS what the production VPS
serves (nightly build output, not a separate deploy artifact) — a render of
`site/sector_central.html` at a pinned, named commit, with the complete
same-origin asset closure the page actually requests, is the honest,
reproducible production baseline: commit-addressed and byte-verifiable,
which a live screenshot is not.

`prod-live-anon-overview.png` (below) is kept as the one counter-example
receipt: the regwall finding above, and the fact that Overview is the one
view the anonymous/gated flow renders at all — captured live from
`https://www.mastermind-x.com/sector_central.html` on 2026-08-21, before this
pinned-commit method existed. It was renamed from
`prod-desktop-dark-en-overview.png` (its original filename) so the
`prod-desktop-dark-en-*` slot could be re-captured by the uniform local
method below, alongside the five other views this method makes possible for
the first time.

## Method

1. **Extraction.** Every same-origin asset `site/sector_central.html`
   references (script `src`, `link href`, and the runtime JSON/JS artifacts
   the six views `fetch()` at mount) was extracted with
   `git show <commit>:site/<path>` into a local mirror directory, preserving
   relative paths. No recompute, no reformatting — each file is the
   byte-identical git blob at the pinned commit. `?v=<hash>` cache-bust query
   strings on `<script>`/`<link>` tags were stripped when mapping URL to
   mirror path (Python's `http.server` ignores the query string when
   resolving a file, so the bare relative path is sufficient); the files
   themselves are unmodified.
2. **Closure discovery — iterative.** The mirror was served locally
   (`python3 -m http.server`) and driven with headless Chromium via
   Playwright (`playwright-core`, Chromium build cached at
   `~/Library/Caches/ms-playwright/chromium-1234`). Each of the six views was
   loaded fresh and console/network activity inspected for local 404s; every
   additionally-requested same-origin path was extracted from the same
   pinned commit and the probe re-run. This repeated until all six views
   mounted with **zero local 404s**. Cross-origin/third-party requests
   (fonts CDN fallback edge cases, analytics, etc.) were allowed to fail
   freely per the commission — nothing remote was fetched into the mirror.
3. **Capture.** For each view: a **fresh** full-page navigation to
   `http://127.0.0.1:<port>/sector_central.html#<view>` (the hash is read at
   boot by the router, so a fresh load — not an in-page hash change — avoids
   the SPA same-document-navigation trap); `localStorage.theme='dark'` and
   `localStorage.lang='en'` seeded via `page.addInitScript` before any page
   script runs; viewport **1440×900**, **device scale factor 2**,
   `colorScheme: 'dark'`; wait for `load` then a bounded `networkidle`
   (8s timeout, non-fatal) plus a fixed settle; scroll through the active
   `section.si-view[data-view="<view>"]` in six wheel steps to trigger
   lazy-mounted charts/treemaps/tables, settle again, then scroll back to the
   section's top; screenshot **section-scoped** on the live
   `section.si-view[data-view="<view>"]` element handle (not a full-page or
   viewport screenshot) so the PNG bounds are exactly the mounted view.
4. **Verification.** Each PNG was read back and visually confirmed to show
   its named view's real, populated content (not a loading/error/blank
   state) — see the per-view notes below.

### Exact commit

```
23ce52c829ae60c5dda7229820df5a608e90ccd9
```

`git rev-parse HEAD` in this worktree at capture time. Verified no commit
between the start of this capture session and this pin touched `site/`
(`git log --oneline <session-start-sha>..<this-sha> -- site/` = 0 commits),
so every extracted byte is consistent with this single pin. Independently
verified: `git show 23ce52c829ae60c5dda7229820df5a608e90ccd9:site/sector_central.html`
is SHA-256 `fbdcfd14b1c78bd410bfb2673e79cba3785c5c0cc5073e44b6c661a38aa719ab`,
identical to the mirror's `sector_central.html`.

### Settings

| axis | value |
|---|---|
| viewport | 1440 × 900 |
| device scale factor | 2 |
| color scheme | dark |
| `localStorage.theme` | `dark` |
| `localStorage.lang` | `en` |
| browser | headless Chromium (`playwright-core`, `chromium-1234`, "Google Chrome for Testing") |
| navigation | fresh full-page load per view, `#<view>` hash in the URL at load time |

## Asset closure (78 files extracted from the pinned commit)

`sector_central.html` itself, plus:

**Scripts/styles/icons referenced by `<script src>` / `<link href>`** (32):
`account.js`, `apple-touch-icon.png`, `assets/css/{1bf96191,29d62e93,307c6f26,5df43e9f,6865a3c5,76831d17,9be9b760,a039f61e,a1ddfd2f,add725b2,fbd430cb}.css`,
`cycle.css`, `dashboard-icons.css`, `desk_watch.js`, `favicon.ico`, `favicon.svg`,
`forming_narratives.js`, `heatmap.js`, `lightweight-charts.js`, `live.js`, `live_config.js`,
`logo_config.js`, `macro-desk.css`, `mm_charts.js`, `nav_market.js`, `navigation-refresh.css`,
`product-nav-icons.css`, `rotation_events.js`, `sector_central_data.js`, `sector_cycles.css`,
`sector_cycles.js`, `sector_cycles_data.js`, `sector_cycles_dna_data.js`, `sector_cycles_narr_data.js`,
`sector_cycles_series_data.js`, `si_workspace.js`, `stock-logos.js`, `subsector_rotation.js`,
`subsectors.js`, `theme.css`, `theme.js`, `time_machine.js`

**R3A fixture-list producer JSON (16 of the 17 fixture entries — `correction/UNREPRESENTED.md`
is an authored doc, not a `site/` path, per `research/reference_integrity/mastermind-xpv2-sector-r3/fixture/PROVENANCE.md`)**:
`sectordata/sector_central.json`, `premiumdata/sector_central.json`,
`basketdata/action_board.json`, `basketdata/baskets.json`, `basketdata/narrative_emergence.json`,
`marketdata/subsector_confluence.json`, `marketdata/subsector_confluence_nasdaq.json`,
`marketdata/subsector_confluence_russell.json`, `marketdata/basket_confluence.json`,
`marketdata/rotation_events.json`, `marketdata/sector_fragmentation.json`,
`marketdata/subsector_rotation.json`, `basketdata/oracle_turn_desk.json`,
`basketdata/oracle_tape_onset.json`, `marketdata/index_leadership.json`,
`basketdata/si_handoff.json`, `oracledata/tm_manifest.json`

**R3B fixture-supplement producer files (the 4 real `site/`-relative paths of the 5-entry
supplement — `fragments/sc_flows.html` is an extracted HTML substring, not a separate
`site/` path)**: `sector_cycles_data.js` (also listed above under scripts),
`marketdata/sp500_heatmap.json`, `basketdata/etf_pulse.json`, `basketdata/vol_sentiment.json`

**Discovered during iterative closure (not named by either provenance doc — found via
live 404 probing against the six mounted views)**: `fonts/Inter-{400,600,700,800,900}.woff2`,
`live/shock_state.json`, `live/quotes.json`, `live/overlay.json`, `live/basket_pulse.json`,
`policy_lever.json`, `basketdata/theme_extension.json`, `basketdata/pulse.json`,
`marketdata/nasdaq_internals.json`

Total mirror size: ≈11 MiB, 78 files. All six views mounted with **zero** local
404s after the full closure above was assembled (verified by a final probe
pass with console/network listeners attached).

## Per-view mount notes

- **Overview** — `section.si-view[data-view="overview"]` mounted, rendered
  height 1513px (CSS px). Act-Now board (five lanes), Bottoming Watch strip,
  self-grader, hero/handoff context all populated with real data.
- **The Map** — mounted, rendered height 3602px. Quadrant scatter, sector
  rotation-clock chart, and the 11-row per-sector gated-read board all
  populated.
- **What's Moving** — mounted, rendered height 3651px. Rotation Events board,
  whole-market rotation map (269 subsectors), turns-this-week table, track
  record, and Desk Watch all populated.
- **Money & Breadth** — mounted, rendered height 2135px. Breadth cards,
  sector-ETF flow table, S&P 500 heat treemap, and index-leadership strip all
  populated.
- **Explore** — mounted, rendered height 2140px. Basket performance table
  (49 baskets), rebased performance chart, Rotation Time Machine section
  heading all populated.
- **Confluence** — mounted, rendered height 5636px. Universe tabs
  (S&P/Nasdaq/Russell/Baskets), rotation-read header, stock picks,
  leadership panels, sector backdrop, and the full 61-row subsector table all
  populated.

## Known, non-blocking production console error (not a mirror artifact)

Every capture logs one `PAGEERROR: renderFormingNarratives is not defined`.
This is a genuine ordering defect in the production template, not an
artifact of the local mirror: `sector_central.html` loads
`forming_narratives.js` with the `defer` attribute
(`<script src="forming_narratives.js?v=..." defer></script>`) and the very
next `<script>` element calls `renderFormingNarratives({ base: "basketdata/" })`
synchronously — a deferred script executes after DOM parsing completes,
*after* a following non-deferred inline script, so the inline call always
throws a `ReferenceError` on first paint, on the live site as well as here.
It does not block any of the six views from mounting or rendering their real
content (confirmed by direct visual inspection of all six PNGs), so it was
left exactly as production ships it — this evidence set faithfully
reproduces the production behavior, defect included, per the FROZEN SPEC
("no patching or script injection").

## Files in this directory

| file | capture method | source |
|---|---|---|
| `prod-desktop-dark-en-overview.png` | pinned-commit local render (this doc) | `23ce52c829ae60c5dda7229820df5a608e90ccd9` |
| `prod-desktop-dark-en-map.png` | pinned-commit local render (this doc) | `23ce52c829ae60c5dda7229820df5a608e90ccd9` |
| `prod-desktop-dark-en-moving.png` | pinned-commit local render (this doc) | `23ce52c829ae60c5dda7229820df5a608e90ccd9` |
| `prod-desktop-dark-en-money.png` | pinned-commit local render (this doc) | `23ce52c829ae60c5dda7229820df5a608e90ccd9` |
| `prod-desktop-dark-en-explore.png` | pinned-commit local render (this doc) | `23ce52c829ae60c5dda7229820df5a608e90ccd9` |
| `prod-desktop-dark-en-confluence.png` | pinned-commit local render (this doc) | `23ce52c829ae60c5dda7229820df5a608e90ccd9` |
| `prod-live-anon-overview.png` | live anonymous-visitor capture, 2026-08-21, from `https://www.mastermind-x.com/sector_central.html` | production VPS (live, gated) |

All six `prod-desktop-dark-en-*` files were captured together in one session
by the method above, so they are methodologically uniform with each other.
`prod-live-anon-overview.png` uses a different method (live capture, kept
deliberately) and is the receipt for the regwall finding — it is not claimed
to be methodologically uniform with the other six.
