# Site-access asset census — open shells, gated assets (2026-08-11)

**Defect class.** The 2026-08-04 operator change opened every `*.html` shell on
www.mastermind-x.com to anonymous visitors. Assets stayed DEFAULT-DENY: Caddy
`@reg_asset` routes any non-HTML path not named in `config/site_access.yml`
through the registration wall. A page whose CSS/JS was never promoted with its
shell therefore serves a **200 whose presentation and renderer assets all 401** —
an unstyled, non-functional skeleton of a product, which protects nothing a
stranger wanted and advertises nothing we sell.

Two pages had already been healed one at a time — `fundamental_forensics.html`
(see the block comment in `config/site_access.yml`) and `stock.html`
(PR #5409). This census asks how big the class actually is.

## Method

`site/**/*.html` (4,596 rendered pages) parsed for `<script src>`,
`<link rel=stylesheet|preload|modulepreload>`, `@import`, and literal
`.src=`/`.href=`/`import()` injections, following one hop through public JS/CSS
(the `theme.js` → `mm_brain.js` shape). Every reference resolved to an absolute
site path and classified against `public.exact` / `public.prefixes`.
Non-literal injections were swept separately by grepping `.src =` assignments in
hand-written root JS.

Every verdict below was then **confirmed live and anonymously** (no cookies)
against production, not inferred from the repo.

## Headline numbers

| | |
|---|---|
| Rendered HTML pages | 4,596 |
| Asset references resolved | 58,714 |
| References to a **non-public** asset | 6,480 |
| Distinct gated assets referenced by open shells | **69** |
| Pages carrying ≥1 gated asset | **4,578** |
| …covered by PR #5409's seven promotions | 4,228 |
| …**remaining after #5409** | **350** |
| Referenced-but-missing assets (404 class) | 0 |

The boundary itself is sound: `?v=` does **not** bypass the gate (tested across
9 URLs including `/premiumdata/`), and every gated asset returns a clean 401.

## A near-miss worth recording: `terminal_overlay.js`

The census flagged this as the next `mm_brain.js` and it was **wrong**. Recorded
because the resemblance is the trap, and it was one verification away from
shipping an unjustified widening.

Everything in the pattern matched: `site/theme.js` builds
`_mmOverlaySrc = new URL('terminal_overlay.js', …)` (theme.js:288),
`prewarmTerminal()` (theme.js:352) calls the loader for **every** visitor
(`mmTerminalOn()` is `window.MM_TERMINAL !== false` — on by default, anonymous
included), and `/terminal_overlay.js` returns a clean 401.

It is still never fetched. `scripts/site_assets.py` **bundles the overlay source
into the emitted `theme.js`** — the block comment at theme.js:5475 says so
outright ("Maintained separately and bundled onto the emitted theme.js") — where
it runs as a top-level IIFE and sets `window.MDXTerminalOverlay` synchronously,
so `loadTerminalOverlay`'s guard (theme.js:295) short-circuits before any idle
callback fires. Confirmed three ways: the **live** `theme.js` is byte-identical
(sha256) to the repo copy and contains the inline definition; a real anonymous
page load requests no `terminal_overlay` resource at all; and the standalone
file's own copy self-guards with `if (window.MDXTerminalOverlay) return;`.

**The lesson generalises to this whole census:** fetching an asset by hand and
seeing a 401 does not show that a page needs it. Only the page's own request
list does.

## What the census found that a file-by-file read would not

`theme.js`'s other injected assets (`navigation-refresh.css`, `stock-logos.js`,
`logo_config.js`, `account.js`, `onboard.js`) are all already public, so
`mm_brain.js` — already being promoted by PR #5409 — was the only genuine
estate-wide instance of the injected-and-gated shape.

## Failure modes, verified live

1. **RENDER-CRITICAL — unstyled skeleton.** `cycle.html`: `cycle.css?v=4` 401s
   and loads **0 rules** (`document.styleSheets` → BLOCKED). 615 of the page's
   8,392 characters render; the rest sits in 11 `display:none` blocks awaiting a
   renderer that also 401s. No chart, no cards, no locked state.
2. **Wrong-paint — worse than blank.** `bonds.html` and 11 sibling pages ship
   their figure geometry **inline in the public HTML**, but `illus.css` (which
   sets `.ilx-path{fill:none;stroke:currentColor}`) 401s. Computed style on the
   live page is `fill: rgb(0, 0, 0)` — the SVG default — so the yield-curve
   figure renders as a **solid black blob**. Confirmed by screenshot and by
   `getComputedStyle`.
3. **Empty shell.** `watchlist.html`: all its renderer scripts 401; the entire
   rendered body is **245 characters** — title, subtitle, "Portfolio ?",
   "as of —", export/import, footer. No error, no sign-in, no explanation.
4. **Misleading error (the `stock.html` "NOT IN LIBRARY" pattern).**
   `government_revenue.html` prints "Link status unavailable" ×6 and
   *"Showing the first 2 governed records while the complete workspace is
   unavailable."* with a "Retry full workspace" button, and
   `hasSignInAffordance: false`. It reads as an **outage**, not a gate.
   A second recurrence sits at `site/tech_lab.html:1501`:
   `if (bars.length < 5 || typeof LightweightCharts === 'undefined')` renders
   *"Real bars unavailable for `<TICKER>`."* — a **data** claim standing in for a
   **library-load** failure. The same file's other two branches are honest
   ("Charting library failed to load — the rest of the page is unaffected.",
   tech_lab.html:1988 / :2161).
5. **Silent.** All 53 `plotly-2.32.0.min.js` pages install a queueing shim
   (`window.Plotly = {newPlot, react, relayout}` pushing into `window.__plotlyQ`,
   e.g. `site/history.html:54`) so calls buffer until the real bundle loads. The
   bundle 401s, so the queue never drains: every chart call is swallowed with no
   error and no empty state. Verified live — `window.Plotly` has exactly three
   keys and the script fetch reports `encodedBodySize: 0`.

## Intended gating — confirmed, NOT a defect

These are data payloads baked into `.js` files. Their 401 is the product
boundary working as designed; promoting any of them would be a leak.

| Asset | Payload |
|---|---|
| `cycle_data.js` | 23 curated cycle cards with forward forecasts (`nextTurn`, `central`, `low`, `high`), `phase`, `pos`, `confidence` |
| `cycledata/cycle_engine.js` | 23 cycles, per-band price series, 23 tripwires, `tolerance_ledger` exposing engine-vs-analyst deltas |
| `markets_data.js` | 11 national market cycles with levels, ATH, `pos`, `phase`, `trailingPE`, `cape` |
| `marketsdata/markets_engine.js` | 10 markets with `signal`/`stance`/`pos_v2`/`phase_v2` + forward projections. **Zero functions** — the "engine" name is a trap, not a description |
| `sector_cycles_data.js` | ~79 instruments; per record a 464-point oscillator + graded `timing_state` / `action` |
| `sector_cycles_china_data.js` | 31 sectors + 22 baskets with `signal: "BUY"`, `action`, and a `sleeve_factor` **sizing** input |
| `country_cycles_data.js` | 24 country sectors + 7 baskets, `timing_state` / `action` |
| `sector_central_data.js` | 11 sectors + 49 baskets with `conviction.score`, `label_en`, confluence counts, reasoning ladders |
| `sector_central_china_data.js` | 31 Shenwan sectors + 22 baskets, `conviction.score`, `rs_rank` |
| `measurementdata/measurement_data.js` | Gate ledger, truth ledger, prediction layer — **see the correction below** |
| `regimedata/regime_prior.js` | One record: quad scores, `confidence`, `flip_condition` with `pending_quad`/`pending_days`. Marginal (the quad *label* is already public on macro.html) but correctly gated |

**Correction to a sub-agent finding.** A reviewer reported `measurement_data.js`
as a *vacuous* gate — "every probe already ships in the public
`measurement.html`" — and recommended promotion. That is wrong, and the
recommendation is rejected. Measuring the whole payload rather than a hand-picked
sample: of 617 wordy string literals in the file, **214 (34.7%) appear nowhere in
`measurement.html`** — internal study keys (`KG-3`, `CC-2`, `CC-3`, W04/W24/W42/W51),
verdicts ("REFUTED-LEANING", "promoted_null", "FAIL / falsified across all three
engines"), `n_stamps` breakdowns and forward-log accrual dates. The gate is real.
It stays.

## Payload-free but NET-ZERO — deliberately not promoted

Promoting these would change nothing an anonymous visitor sees, because every
data source they read stays gated. A promotion that ships bytes which draw
nothing is added public surface for no user benefit.

| Asset | Pages | Why net-zero |
|---|---|---|
| `wh_banner.js` | 243 | Payload-free (all rows fetched, `textContent` only, degrade-silent by design). But **both** feeds — `/wh_banner.json` (per-alert `tickers[]` with `direction`/`chg_pct`) and `/rr_banner.json` (`score`, `odds_pct`, `lift`, `ramp`) — are payload-bearing and stay gated. There is no skeleton here: the banner is invisible-by-absence, nothing shifts, nothing errors |
| `mm_charts.js` | 8 | Zero-dependency SVG charting engine, no network calls. Every spec source (`cycle_data.js`, `cycle_engine.js`, `markets_data.js`, `markets_engine.js`, `sector_cycles_data.js`) is payload-bearing and stays gated |
| `stockdata.js` | 2 | 147-line, 29-function fetch helper; **zero** baked rows (verified: no array-of-object literals, no string literal over 40 chars). Reads `stockdata/index.json` and `<market>stockdata/<T>.json`, which stay default-deny. Its one public consumer (`heatmap.js:420`) already guards and falls through. Name collides with the gated `stockdata/` store — a documentation hazard worth noting |

## Promotions proposed

All are payload-free presentation or fetch-clients whose every signal-bearing
read stays outside the allowlist — the `fundamental_forensics.css|js` standard.
**Promoting the workbench changes nothing about who can read the work.**

### Vendor charting bundles

`plotly-2.32.0.min.js` (53 pages) and `lightweight-charts.js` (v4.2.0, 21 pages)
are unmodified third-party bundles. Verified rather than assumed: both are
**byte-identical (sha256) to the upstream npm artifacts**
(`plotly.js@2.32.0/dist/plotly.min.js`,
`lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js`),
carry a single license banner and a single IIFE, and contain zero project
identifiers. Neither makes a same-origin data read.

These are **real fixes, not cosmetics**: on both families the plot payloads are
already inline in the public HTML shell (`Plotly.newPlot(...)` with the series
baked in; `createChart(...)`/`setData(...)` on the sector pages), so the charts
actually draw once the renderer loads — and no data moves, because the data was
already outside the wall.

`lightweight-charts-v5.js` is a **separate file**, not a replacement. PR #5409
promotes v5 for the analyzer pages; all 21 pages here load the v4 file and are
untouched by it.

### Page presentation

Every one of these was checked for `content:` data, `url()` refs, entity-keyed
selectors (`[data-ticker]`/`[data-symbol]`/`[data-sector]`) and numeric data
custom props (`--score`/`--rank`/`--pct`). **Zero hits on every probe, in every
file.** None has any `url()` at all, so none pulls in a further gated asset.

| Asset | Pages | Effect of the 401 today |
|---|---|---|
| `cycle.css` | 7 | RENDER-CRITICAL — owns `body` layout plus `.cyc-*`; `scripts/check_nav_gap.py` pins pages styled by it to inherit the nav gap from its `body` rule, so the header gap collapses too |
| `sector_cycles.css` | 5 | RENDER-CRITICAL — owns `.sc-tabs`, `.scc-universe`, `.sc-bask-*`, `.sc-leg-*` |
| `macro-desk.css` | 14 | DEGRADED — desk skin over `theme.css` + `assets/css/*` |
| `odds.css` | 1 | RENDER-CRITICAL — defines its own `--od-*` palette (incl. the zh 红涨绿跌 swap and light-theme remap) and `body` background; odds.html carries 114 `od-*` usages |
| `capital_structure.css` | 1 | RENDER-CRITICAL — 82 `cs-*` usages. Its payload source `/capital-structure-data/` is `premium.enforced_early` and is untouched by any CSS decision |
| `markets.css` | 1 | RENDER-CRITICAL for the panel grid; markets.html also loads `cycle.css`, so the two fail together |
| `government-revenue-parity.css` | 1 | DEGRADED |

Every affected page is **server-rendered**, carrying 8,000–47,000 characters of
already-public static text. This is content we are currently serving unstyled.

### The `illus` pair — must move together

`illus.css` + `illus.js` (12 pages) are one unit, and a **half-promotion is worse
than neither**:

- `illus.css:311-330` puts the pre-reveal start state behind
  `@media (prefers-reduced-motion: no-preference)` — `.ilx-path` gets
  `stroke-dashoffset`, and `.ilx-area`/`.ilx-dot`/`.ilx-bar`/… get `opacity: 0`.
- The ink only draws once `.ilx-in` lands (`illus.css:332-338`), and
  **`illus.js` is the sole writer of `.ilx-in`** (illus.js:11, :19, :59).

So: **CSS only** → every figure is permanently blank for anyone not running
reduced-motion. **JS only** → figures stay solid black (`fill:none` never
applied). **Both** → correct. `illus.js` makes zero network calls; it is one
IntersectionObserver plus `window.ilxMount`/`ilxReveal`. The SVG path geometry is
already inline in the public HTML, so neither file moves the data boundary.

### The 37 renderer scripts that were examined and NOT promoted

Every per-page renderer on the affected pages was classified. **None is
promoted**, on three distinct grounds:

- **Payload-bearing (2).** `cycle_i18n.js` (33 KB) and `markets_i18n.js` (44 KB)
  are not translation tables — they are the product verdict in Chinese, keyed by
  cycle/market id, carrying `read`, `falsifier`, `phaseLabel`, `drivers` and
  dated turn maps with hard levels and published position scores. Self-contained:
  a zh reader would not need the engine files to read the whole book. These sit
  with the `*_data.js` family in the table above.
- **Net-zero (≈30).** Payload-free renderers whose every data source stays
  gated — `cycle_app.js`, `markets_app.js`, `sector_cycles.js`, `subsectors*.js`,
  `subsector_rotation.js`, `radar_panel.js`, `odds.js`, `ai_desk.js`,
  `aibrief.js`, `mastermind.js`, `capital_structure.js`, `allocation_scorecard.js`,
  `ai_desk_thematic.js`, `forming_narratives.js`, `china_risk_state_live.js`,
  `vector_chart.js`, `vector_timemachine.js`, `risk_core.js`,
  `factor_exposure.js`, `market_books.js`, `watchstore.js`, `watchlist.js`,
  `portfolio.js`, the four `government-revenue-*.js`, and others. Promoting any
  of them downloads bytes that draw nothing — and in six cases would light up a
  misleading string that is currently unreachable (see below).
  Two specifics worth naming: the `watchlist`/`portfolio` pair is **not** rescued
  by being localStorage-backed, because the localStorage book lives inside the
  gated `watchstore.js` and `watchlist.js` throws on an unguarded
  `window.SD.loadIndexes(...)` before its first render; and `watchstore.js` is a
  *customer-data* Supabase client rather than a market-data client, a different
  risk class that the current standard does not speak to at all.
- **Would reveal paid rows (3).** `si_workspace.js`, `si_workspace_china.js` and
  `baskets_desk.js` are the only three that would materially change what an
  anonymous visitor sees — by rendering premium rows that are **already sitting
  in the public HTML**. That is a pricing ruling, not a skeleton repair. See
  finding #5 below.

## Flagged, NOT fixed here

1. **Five pages degrade dishonestly and need a locked state, not a promotion.**
   `cycle.html`, `markets.html`, `country_cycles.html`, `sector_cycles.html`,
   `sector_cycles_china.html` ship 9–14 empty id'd containers with **zero
   `<noscript>`, zero locked state, zero `console.error`, and no
   `tier_preview.js`**. Because renderer *and* data are both gated, nothing
   throws — the visitor gets nav + headings + a blank content region, which reads
   as "there is nothing here" rather than "you cannot see this". That contradicts
   the `config/site_access.yml` header's own claim that "tier_preview.js paints
   the locked slot where the paid rows sit". The correct shape already exists in
   `heatmap.js:606-626`, which probes `/api/regwall/check` and fails closed to a
   locked slot. Promoting the CSS above makes these pages *styled* rather than
   raw, which is strictly better, but it is not the fix — the fix is the
   tier-preview locked state, and it is a per-page template build.
2. **Two misleading-error strings** (`government_revenue.html`'s "the complete
   workspace is unavailable" / "Link status unavailable", and
   `tech_lab.html:1501`'s "Real bars unavailable for `<TICKER>`.") should be
   split so an auth/load failure reads as locked, not as absent data. The
   `tech_lab.html` one is a one-line fix: separate the `bars.length < 5` arm from
   the `typeof LightweightCharts === 'undefined'` arm.
3. **The per-ticker graded emit is readable without auth from the public R2
   bucket.** This one is a live contradiction of this policy file's own text.
   `config/site_access.yml` states that "every per-ticker
   `<market>stockdata/*.json` graded emit" still gates, and through Caddy it
   does: `/stockdata/AAPL.json` → **401**. But `site/data_base.js` is inlined
   into every page head and monkey-patches `window.fetch` to rewrite
   `stockdata/`, `chinastockdata/`, `hkstockdata/`, `canadastockdata/`,
   `intlstockdata/`, `ohlc/`, `intraday/` and `oddsmatrix/` to a public R2 host,
   bypassing Caddy entirely (mirrored by `scripts/publish_r2.py`). Verified
   anonymously: the same object on that host returns **200** and 112 KB
   carrying `board_score`, `tier`, `fundamental_score`, `forward_tier`,
   `regime_score`, `basket_score`, `conviction`, `risk_sizing`, `composite`,
   `entry_signal`, `sniper` and `verdict_zh`.
   **Not touched here, deliberately:** every stock page fetches through that
   rewrite, so locking the bucket would break the analyzer for paying users
   too. This needs a delivery-plane decision (signed URLs, a gated worker, or
   an explicit ruling that the emit is free), not an allowlist edit.
4. **`/api/government-revenue/*` is unauthenticated.**
   `app/government_revenue.py` carries **zero** `Depends` across 20+ routes;
   its sibling `app/capital_structure.py` has six. Caddy excludes `/api/*` from
   `@reg_asset`, so nothing upstream compensates. Verified anonymously:
   `/api/government-revenue/candidates?limit=2` → **200** with a real
   `government_revenue_candidate_queue.v1` body
   (`mapping_backlog_total: 21`, `company_coverage_count: 21`,
   `award_change_events_visible: 500`), while
   `/api/capital-structure/v1/coverage` → **401**. This may well be intentional
   — the underlying facts are public USASpending procurement records — but the
   asymmetry with every other desk is unexplained anywhere in the repo, so it
   should be ruled on rather than left implicit. It is also why no
   `government-revenue-*.js` client is promoted here: the question of whether
   promoting them is a fix or the completion of a leak cannot be answered until
   the API's intent is settled.
5. **Two page families ship paid rows in the public byte stream, hidden only by
   CSS.** `config/site_access.yml` states the rule directly — "the preview shell
   must not contain the payload's rows (the split is the boundary; a
   client-side hide is a marketing wall, not a gate)".
   `sector_central.html` / `sector_central_china.html` carry ~24 KB / ~37 KB of
   server-rendered ranked lanes, scores, breadth and named leaders inside
   `<section class="si-view">` — "ACCUMULATE" alone appears 10× in the served
   US file — kept off-screen only by `.si-view{display:none}` in
   `site/assets/css/*.css`, which is under the **public** `/assets/css/` prefix.
   `baskets_canada/hk/intl.html` inline 425–463 KB `const BASKETS = {…}`
   literals with per-member `ret_ytd`, and their own inline (therefore public)
   script already renders the tables and cards.
   The fix is to take the rows out of the shell, not to change the boundary —
   and it must land **before** `si_workspace*.js` or `baskets_desk.js` is ever
   promoted, since those are exactly the files that would unhide them.
6. **`markets_data.js` carries two contradicting reads of the same market.**
   `scripts/refresh_markets_now.py` patches only `level`/`asOf`/`ath`/`athDate`/
   `pctFromATH`; the curated `now.read` prose is never refreshed, so a card can
   show structured fields at one date and prose at another ~7 weeks apart.
   Unrelated to the serving boundary — filed separately.
7. **Six more misleading-error strings**, all asserting a data/build/infra fact
   where the real cause is a 401 — and all currently UNREACHABLE because the
   script that renders them 401s first. They become live the moment the
   corresponding client is promoted, which is a further reason none of those
   clients is promoted here:
   `subsectors.js:506` / `subsectors_china.js:265` "No data yet — run the
   nightly build." (also leaks an internal ops instruction into customer copy);
   `mastermind.js:19` "Snapshot pending — the local Mastermind server hasn't
   pushed yet, or you're offline." (blames the visitor's connection);
   `ai_desk.js:166` "AI desk note unavailable right now — it regenerates daily
   after the close."; `radar_panel.js:1879` "The radar has no read to show right
   now."; `odds.html:323` "Odds data is unavailable right now. The nightly build
   will refresh it."; `allocation*.html` `#td-empty` "Live desk note is not
   generated yet."
8. **`country_cycles_data.js` and `sector_cycles_data.js` both assign
   `window.SECTOR_CYCLES`.** Safe today because no page loads both; one added
   `<script>` silently rebinds the global.
