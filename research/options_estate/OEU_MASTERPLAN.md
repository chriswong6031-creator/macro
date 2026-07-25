# OEU — Options Estate Unification masterplan (by Fable, 2026-07-25)

Program: unify the Macro Dashboard options/flow estate around ONE canonical workspace, finish the
quantedoptions.com amalgamation in the Terminal (Wave 3), cross-pollinate the two estates, wire
display-tier options context into Prophet, and close with an adversarial bug wave. Successor to
`research/quanted_options/MASTERPLAN.md` (Waves 1–2 shipped: macro #3447/#3451/#3452/#3461,
terminal #197/#198/#199). Census evidence: 9-lane workflow 2026-07-25 (8 sonnet inventories +
1 opus UX review); first-party visual pass over all 8 pages; verification greps on current main.
Prior art ratified in refined form: `EOD_CONSOLIDATION_BLUEPRINT_20260723.md` (this dir — recovered
from an uncommitted charting-app audit doc; its correctness findings were re-verified 07-25, its
IA adopted with changes, its relitigations of this week's shipped revamps rejected).

## §0 ACCEPTANCE GATES (all lanes; phrased "not done unless")

0.1 **Fresh end-to-end happy path, zero manual workarounds.** A race you reload around is a bug you own.
0.2 **UI lanes: crops are COMMITTED files** (`docs/pr-crops/oeu-<lane>/` in the repo being changed),
    referenced from the PR body, light+dark, EN+ZH where the surface is bilingual. tmp screenshots
    do not count (Wave-2 Lane-E lesson).
0.3 **No child self-merge of flagship UI first passes** (M-CMD workspace, T-C surface tab): PR +
    crops come back to the commissioning session for review-then-merge. Fix/truth lanes (T-A, T-D,
    M-FIX, M-XP, M-PRO, T-B, T-E) may merge after green CI, but must post PR# + crops first.
0.4 **Tests: run the downstream suite, not just your new file.** Macro: the repo pytest lanes your
    files feed (plus `python -m scripts.check_template_site_sync --fix` when touching paired
    assets; regen blocklists if you touch DO_NOT_REBUILD). Terminal: `npm test` + `npm run build`.
0.5 **Epistemics:** display-tier ships freely; nothing new feeds rank/size/gate; the word
    "validated" only where already CI-sanctioned; LLMs never originate signals. No new fused
    composite across positioning keys (MSP-R3 / Signal-Commons / DNR §1 Ivory-Hill row). DOI,
    skew-deceleration, signed-charm stay dead/display-only per DNR.
0.6 **Bilingual:** every new EN string has its ZH pair via the page's existing `t()`/`l-en/l-zh`
    idiom; zh direction colors via `--up/--down` tokens only (红涨绿跌 flips by token, never
    hardcoded rgba). No translated text in `title=` attributes.
0.7 **Worktrees:** macro lanes branch off fresh `origin/main`; charting-app lanes off fresh
    `origin/master` in their own worktrees under the repo's `.claude/worktrees/`. NEVER touch either
    primary checkout's git state (charting-app primary is 163 commits behind and occupied).
0.8 **Render budget:** no new heavy compute on the nightly render path. New macro build steps must
    be O(seconds) re-serialization of existing stores, and data must build BEFORE the page renders
    in the same generation (market_structure DAG lesson).

## §1 Verdict — what the census established

**Individual macro pages are mostly fresh and good** (#3341 gex remaster, #3226 flow desk, #3229
intraday flow, #3224 flow leaders, #3314 darkpool, all this week). The estate-level failures:

1. **No front door.** Landing + start hub link to NONE of the 8 pages; the nav flyout is the sole
   discovery surface, a flat list of 8 with taglines doing all the work.
2. **Identity collisions.** Three US pages named "Flow" (US Options Flow / Intraday Flow Tracker /
   Flow Leaders); dealer positioning split across gex.html (per-name) and market_structure.html
   (index regime); movers.html is not an options page at all; darkpool is equities off-exchange.
3. **Cadence unsignposted.** EOD desks and a ≤15-min tracker sit side by side with no family-level
   freshness story.
4. **One page violates doctrine:** flow_leaders.html ships raw research slugs (LEGS chips `FlowZ`,
   `TSBrd`, `NotTrap`) — banned vocab on a glance surface.
5. **Real correctness bugs** (verified on main 07-25): flow_leaders washout-flip counts cumulative
   not consecutive negatives and back-searches to the earliest flip ever (Board B admits ~everyone);
   market_structure `week_map` never emitted (Weekly Range perpetually warming up) + DAG renders
   before its data builds + a tooltip claims a 70/30 SPX/SPY blend the code doesn't implement;
   screener `pain_dist_pct` divides by max-pain while wall distances divide by spot.

**Terminal estate** (post Waves 1–2): 11-tab OptionsHubView with one dead tab (`vol`); flagship
surface pane buried in the Tickers tab's right column; the GEX-desk expiry dropdown is a dead
control; replay time-travels only the surface pane; plus a ranked bug ledger (§3).

**Cadence boundary (ratified, from the 07-23 blueprint):** Terminal explains what is changing NOW;
Macro explains what settled at the close, what changed across sessions, and what deserves research
for tomorrow. The two estates share data contracts and deep links, not surfaces.

## §2 The macro consolidation ruling

**Build ONE canonical workspace — `options.html` "Options" — with four modes,** assembled at build
time from the EXISTING stores (no new engines, no legacy-page rewrites):

- **Daily Brief** (default): close receipt band (session · OI vintage · coverage · quality) →
  posture chips co-displayed, never fused (Market Weather ✓validated / SPX shock-absorber state /
  tape intensity / 0DTE share) → what-changed chips → index close row (SPX/SPY/QQQ/IWM: regime,
  flip dist, walls, expected move) → sector concentration bars → biggest bets → names-for-tomorrow
  rail (recurrence leaders + FIXED washout turns + near-flip screener preset) → Terminal handoff CTA.
  Source: `site/flow_desk.json`, `data/market_structure/latest.json`, `site/vol/regime.json`,
  `site/gex/{SPX,SPY,QQQ,IWM}.json`, `site/flowleaders/leaders.json`, screener rows.
- **Scanner**: the options_screener table (same columns/views/presets) + per-row as-of age +
  ticker deep-link into Ticker mode. Source: new `site/screenerdata/rows.json` export (M-XP).
- **Ticker** (Positioning & Volatility): the gex.html per-name workbench (price ladder, three
  reads, flow card, raw-structure shelf) keyed by `?t=`/hash + "Open live in Terminal ↗".
  Source: existing `site/gex/<T>.json` + `site/flow/<T>.json` client fetch.
- **Leaders**: corrected Boards A/B + the ETF strip (its single home now). Source: leaders.json.

Payload law: Brief context baked inline; Scanner/Leaders/Ticker payloads lazy-fetched on mode
activation (no JS-injected `<script>` loaders — plain fetch; asset-stamping trap). Renderer:
`scripts/build_options_command.py` (new, O(seconds), runs AFTER flow_desk/screener/leaders/
market_structure in the DAG).

**Nav regroup** (`templates/_navlinks.html.j2` + theme.js pair law): flyout trigger becomes
`options.html` — "🧲 Options · one workspace / 期权工作台". Flyout: 4 mode deep links
(#brief/#scanner/#ticker/#leaders), then an "Adjacent desks" group: Intraday Flow Tracker,
Dark Pool Desk, Market Structure. **Daily Movers moves to the US/markets nav group** (it is a
stocks page; sitemap priority 0.7 preserved). The four absorbed pages (gex, options_screener,
flow_desk, flow_leaders) LEAVE the flyout but their URLs stay live (house pattern: no page
deletions, no redirect infra exists) — each gets a slim top banner "This desk now lives in the
Options workspace ↗ <mode anchor>" and keeps rendering for bookmarks/SEO.

**Explicitly rejected:** literal merge of the four legacy pages' HTML into tabs (throws away this
week's revamps, 4-way regression risk); killing any page file; renaming shipped desks (structure
fixes the confusion, not naming); moving intraday_flow to Terminal in this program (real product
question — deferred to §5); relabeling darkpool's #3314 language (operator-sphere, shipped, and
already triple-disclaimed — we only ADD the FINRA short-marking caveat to its methodology shelf
if absent).

## §3 Bug ledger (input to lanes now; final wave re-verifies everything)

Terminal (from the 07-25 opus review — verify in-lane before fixing):
- B1 StrikeLadder PEAK normalizes per-strike bars against the day's AGGREGATE net_gex history —
  cross-quantity; bars collapse. → T-A (re-spec PEAK to an honest computable base).
- B2 optionsAlerts premium-burst z: window mean vs single-obs std (no √w), baseline includes the
  test window, `Math.abs(z)` fires on SLOW tape. → T-D (spec in lane charter; TS + Python + parity).
- B3 Surface grid: cells keyed by `cell.low` under non-uniform price_levels → transparent stripes. → T-C.
- B4 Evolution modal "Expiry breakdown at NOW" uses head-of-day matrix even when scrubbed (PIT). → T-C.
- B5 replayContext: focusin sets hover forever (Space/arrows hijacked page-wide); onEnter/onLeave
  recreated per bind → listener accumulation. → T-B.
- B6 MarketStateCard pin `probability` 0..1-vs-0-100 shape ambiguity (can render 5500%). → T-A.
- B7 Two DTE conventions on one desk (20:00Z vs UTC-midnight). → T-A (single helper).
- B8 `has0Dte` checks only `expiryOptions[0]` (ordering assumption). → T-A.
- B9 SurfacePane `fitContent()` on every frame (zoom reset while scrubbing); ~390 `Date`s per
  mousemove. → T-C.
- B10 Dead `vol` tab key + dead expiry dropdown (no consumer). → T-A (wire it) / T-C (remove key).
Macro (verified 07-25): flow_leaders washout-flip (M-FIX, spec below); market_structure week_map /
DAG order / 70/30 claim / CTA "STYLIZED PROXY" badges (M-FIX); screener pain_dist denominator +
"nan" regime strings + median_depth_days mislabel (M-FIX).

## §4 Lane charters

### Wave 1 (parallel now)
- **T-A · GEX desk truth & expiry lens** (charting-app, builder/opus): wire the expiry selector
  end-to-end (ladder + summary recompute for 0DTE / All / All−0DTE / specific expiry; Σ-buckets),
  Net | Call/Put ladder toggle, per-expiry value columns where payload allows; fix B1, B6, B7, B8;
  tooltip clip (move to fixed layer); hardcoded bar rgba → `--up/--down` tokens (zh flip); route
  MarketStateCard literals through i18n; ladder responsive minimums (375px phone usable).
- **T-C · Surface flagship** (charting-app, builder/opus; NO self-merge): promote Surface+Replay+
  SessionFlow+Evolution into a dedicated hub tab (remove dead `vol` key); quad view (2×2 metric
  grid); 30m agg step; Send-to-chart (pin hovered strike as a price-pane level line); theme engine
  (per-greek color-pair pickers + presets, localStorage, drives METRIC_COLOR_VARS); alert-from-drill
  button in the evolution modal (creates a wall/flip alert via existing client API — do NOT touch
  optionsAlerts.ts, that is T-D's file); fix B3, B4, B9; constrain root input to materialized
  SURFACE_ROOTS with an honest "no surface for X yet" state.
- **M-FIX · macro correctness** (macro, builder/opus): flow_leaders `flow_inflect` → newest valid
  LOCAL pattern `[-,-,-,+]` (consecutive negatives immediately preceding the flip; freshness window
  0–5 sessions; interrupted runs and stale flips fail; tests for `---+`, `--0+`, `---+---`, old
  flip, gaps, short history; Board B membership requires the corrected detector); market_structure
  emit `week_map` (locked Friday close ±1σ/±2σ off expected move) or drop the section, fix DAG
  order (data before render), remove the 70/30 blend tooltip claim, add "model estimate" badge
  beside CTA/vol-control dollar figures; screener `pain_dist_pct` → divide by spot, normalize
  `"nan"` gamma-regime strings at the schema boundary, relabel `median_depth_days` honestly.
- **M-XP · macro data plane for cross-poll** (macro, builder/opus): (a) date-keyed Flow-Surface
  retention — poller writes `live_flow/surface/{ROOT}/{DATE}/…` + a dates index, keep N=10 sessions
  (enables Terminal multi-day replay; keep today-only paths working during transition); (b) mirror
  `site/darkpool_eod.json` + `site/vol/regime.json` to R2 alongside the existing gex_state/flow
  mirrors; (c) export screener rows to `site/screenerdata/rows.json` (for M-CMD Scanner mode);
  (d) flow_desk "how the day unfolded" panel — the completed session's tide curve from the R2
  live_flow store via the existing `window.DATA_BASE` pattern (intraday_flow precedent);
  (e) gex.html per-name "Open live in Terminal ↗" deep links.
- **M-PRO · Prophet options context, display-tier ONLY** (macro, builder/opus): via the five
  audited hook points — prophet-card ⚠ flags (wall-proximity / elevated IV percentile), entry_read
  `caveats` keys (`gex_pin_risk`, `iv_rank_elevated`) following the ENTRY_CAVEAT_EARNINGS pattern,
  a dealer-positioning sentence in `_build_thesis` prose, `_load_gex_walls`-style loaders feeding
  evidence-only keys, and a "structure receipt" on plan cards (chosen contract's spread/OI/IV
  percentile from existing chains store). HARD FENCE (LRV-O9/DNR): nothing enters any K-of-N set,
  state condition, fire rule, sort key, or `select_candidates` — display/caveat/prose only.

### Wave 2 (after W1 merges)
- **T-B · Workspace replay & history** (charting-app): ladder/drawer/session panes subscribe to
  `asOfStamp` (whole-desk time travel); multi-day replay via M-XP(a) dates index (graceful
  today-only fallback); event annotations on the scrubber (FOMC/CPI/open/close bands from the macro
  calendar payload); fix B5.
- **T-D · Scanner belts, alerts truth & UX bag** (charting-app): index/sector belts as
  click-filters on Tape/Screener + Highlights bursts; premium-burst z fix per spec — baseline
  excludes the test window, `z = (winMean − baseMean) / (baseStd/√w)`, one-sided hot-only,
  min-sample guard, identical Python port + parity fixtures (hot fires / slow does NOT / short
  history → null); surface hot-pocket alert type (TS+Python+AlertsView row); AlertsView 401 →
  real signed-out state (not fake empty), delete confirm, trigger note visible on touch;
  TabSkeleton + aria-label i18n; hub responsive pass.
- **M-CMD · the Options workspace** (macro; designer/opus pins spec → builder/opus implements;
  NO self-merge): §2 exactly — options.html 4-mode workspace, nav regroup + movers move, legacy
  banners, sitemap, SEO head, bilingual, payload split, `build_options_command.py` + DAG wiring +
  render tests. Crops: all 4 modes, light+dark, EN+ZH.
- **T-E · Terminal EOD context belt** (charting-app, after M-XP): "Structure" strip on the options
  hub (EOD walls/flip/expected-move/max-pain/IV-percentile from `gexstate:{ROOT}`/`gex:{ROOT}` +
  OI-confirmation read) with clear EOD-vintage labeling; Dark Pool mini-panel from the new
  darkpool R2 mirror (parity masterplan Phase-4 item).

### Wave 3 · Bug hunt (LAST, per operator)
Adversarial reviewer wave over EVERYTHING this program + Waves 1–2 shipped (both repos): verify
§3 residue, hunt fresh regressions (suites, build, fixture drift, i18n leaks, PIT honesty), fix
lanes, then deploys (droplet `terminal-build.sh`; liveflow ops-worktree ritual if poller files
changed; macro via merges) and live verification.

## §5 Deferred (not in this program; do not build without a new ruling)
- Moving intraday_flow's live board into the Terminal (blueprint ask; real product decision).
- Sunsetting the four legacy page URLs into redirects (revisit after workspace proves itself).
- Terminal Leaders/Radar tabs migration into macro Leaders & History (dedup of two ranking surfaces).
- Shared authenticated user-state service (watchlists/saved scans across estates); research API;
  full per-metric provenance objects (adopt the cheap slice: as-of badges + coverage lines).
- OPEX/expiration calendar page; OI-change history map (strike × date) — strong candidates for the
  next EOD program.

## §6 Provenance
Census artifacts: workflow wf_b2cf0efd-1a2 (9 lanes, 2026-07-25); blueprint
`EOD_CONSOLIDATION_BLUEPRINT_20260723.md`; quanted teardown `research/quanted_options/RECON.md`;
Terminal docs `docs/OPTIONS_SUITE_PARITY_MASTERPLAN.md`, `OPTIONS_TERMINAL_UPGRADE_REVIEW_2026-07-23.md`
(charting-app). Waves 1–2 record: memory `quanted-options-program`.
