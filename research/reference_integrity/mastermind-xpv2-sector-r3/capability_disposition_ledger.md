# XPV2-SC-R3A — Capability Disposition Ledger (Deliverable 1)

Program: `WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2` · Wave: `XPV2-SC-R3A`
Frozen spec: `research/reference_integrity/mastermind-xpv2-sector-r3/ADJUDICATIONS.md`
("Capability ledger priors")

Every disposition below follows the fixed law: **everything working is
RETAIN**; **Baskets-tab gateable/thin disclosure** and **correction/revision
representation** are **BLOCKED_DATA** (producer emits no field for either);
**nothing in this wave is REMOVE or RELOCATE** — any candidate for those
requires a new ruling in `ADJUDICATIONS.md` first. No row below invents an
IMPROVE disposition: a recorded defect (A3 Map reco action-tag conflation,
A6 Overview stale-guard fail-open, A7 routing seams) stays attached to a
RETAIN capability as a note, because the capability itself ships and works
today — its repair is filed separately and is out of scope for this wave.

Every row cites the dossier section it is drawn from. Where a dossier itself
carries a GAP (an unopened file, an unconfirmed cadence), that GAP is carried
into the note column verbatim — it is not resolved by inference here.

## Overview

| # | Capability | Disposition | Dossier cite | Note |
|---|---|---|---|---|
| 1 | Six action-lane keys (`buy_now,buy_soon,on_the_run,take_profits,hold,avoid`) folding into five rendered columns (hold+avoid share "Stand aside") | RETAIN | lane A §1, A1 | Fixture-pinned: `scripts/build_sector_central.py:67-73 _ACTNOW_LANES` |
| 2 | Exact EN/ZH lane labels + subcopy (Buy now / Almost ready / In favour — don't chase / Take profits / Stand aside) | RETAIN | lane A §2-3 | Byte-verified against R2 critic's own DAC-006 quotes |
| 3 | Lane header counts computed off the FULL board, never gated ("counts are free, names are paid") | RETAIN | lane A §4 | |
| 4 | Row merge order: theme (basket) rows lead, sector rows follow, within each lane | RETAIN | lane A §5 | Build-time, server-side; not client-resortable |
| 5 | `buy_soon` sector sub-list sorted by `days` ascending | RETAIN | lane A §5 | Only sector sub-list with an explicit sort |
| 6 | Theme row `score` + `perf_20d_rel` numeric fields | RETAIN | lane A §6 | |
| 7 | Sector row qualitative `stat_en`/`stat_zh` chip (no blended score/perf pair) | RETAIN | lane A §6 | Confirms REFUTES DAC-001's "single blended score" pattern claim |
| 8 | Per-sector conviction score (`sectordata/sector_central.json`, distinct artifact from the action board) | RETAIN | lane A §6 | GAP: XLV 23/Reduce figure taken from critic's own quote, not independently re-pulled |
| 9 | Sector row click destination (`US_SECTOR_PAGE` override table → `sectors/<TICKER>.html` fallback) | RETAIN | lane A §7 | |
| 10 | Theme row click destination (`basket/<id>.html`) | RETAIN | lane A §7 | |
| 11 | Bottoming-watch row click destination (href set by producer, consumed verbatim) | RETAIN | lane A §7 | GAP: exact href-construction line inside `engine/us_act_now.py`/`scripts/build_baskets.py` not traced |
| 12 | "+N more" links → `sector_central.html#actnow-section` (same-page anchor, all five lanes) | RETAIN | lane A §7 | |
| 13 | Lane-foot "Drill to stocks →" → `#confluence` in-page view switch | RETAIN | lane A §7 | |
| 14 | Premium gate switch + preview/locked split (`config.yml sector_central_gate: gated:true, preview_rows:3`) | RETAIN | lane A §8, A9 | Currently ON in production |
| 15 | Split computed twice (Python payload + Jinja shell) from the identical source list — shell/payload cannot disagree by construction | RETAIN | lane A §8 | |
| 16 | `premiumdata/sector_central.json` payload, `tier_payload.v1` schema, written unconditionally every build | RETAIN | lane A §8 | preview=3/locked=29/total=44 live at capture |
| 17 | `sector_central.json` payload kept separate from `us_stocks.json` (no shared-file overwrite race) | RETAIN | lane A §8 | |
| 18 | `/premiumdata/` URL-level enforcement ahead of the site-wide paywall switch | RETAIN | lane A §8, A9 | `config/site_access.yml` `premium.enforced_early` |
| 19 | Authenticated hydration flow (`whenAuthSettled` → fetch → `hydrate()` schema/page validation → DOM insert by `data-ab-lane` → `restoreFold` → disclosure-line removal) | RETAIN | lane A §8, A9 | Server always re-decides regardless of client auth state |
| 20 | `si-read-overview` summary strip (`readOverview()`, composed purely from `theme_intel.act_now.buy` length + hero attrs) | RETAIN | lane A §9 | Display-tier only, A7-compliant per in-code comment |
| 21 | Bottoming Watch: strict display-tier/watch-only contract (`signal`/`timing_state` payload fields deliberately never rendered) | RETAIN | lane A §10, capability priors | Pinned by `tests/test_us_act_now.py` in production |
| 22 | Bottoming Watch exact EN/ZH wording (lane title, subcopy, per-row chip, gate-conflict chip, dual-read chip, empty state, null disclosure) | RETAIN | lane A §10 | |
| 23 | Bottoming Watch full-width strip layout under the five lanes, explicitly NOT a sixth action lane | RETAIN | lane A §10 | |
| 24 | Overview hero / "This week's handoff" / "What changed" leadership context, sourced from `si_handoff.json` `theme_context`/`factor_season`/`flow` | RETAIN | lane A §11, A2 | |
| 25 | Hero fallback to generic "US Sector Intelligence" when `si_handoff.json` absent/corrupt | RETAIN | lane A §11 | Fail-soft read, `ctx={}` |
| 26 | Structural separation: no code path connects hero leadership text to action-board lane placement | RETAIN | lane A §11 | Confirms DAC-002's "no code path" verdict — this IS the invariant the design brief must not violate |
| 27 | Overview absolute-clock stale guard (`_dtpState`, 12h threshold vs `Date.now()`) | RETAIN | lane F State 4, A6 | Recorded defect (fail-open on malformed `as_of_utc`) filed separately, not repaired this wave |
| 28 | Zero-vs-missing distinction (`is not none`/`is defined` idioms, never truthiness) | RETAIN | lane F State 2, A6 | |
| 29 | Per-lane empty-state copy via Jinja `{% for/else %}` (genuine zero-length construct, not a string check) | RETAIN | lane F State 3 | Does not distinguish "absent key" from "empty list" — that distinction exists one level up only |
| 30 | Independent fail-soft degrade per secondary source (`ctx`/`action_board`/`_bottoming`/`flows_html`, each with its own fallback) | RETAIN | lane F State 5 | |
| 31 | Fetch-fail / malformed-JSON collapse to one fixed "Data failed to load — please refresh." string | RETAIN | lane F State 6 | Failure causes indistinguishable to the reader by design |
| 32 | 401/403/offline collapse to no-op keeping the server-baked preview + sign-in disclosure line | RETAIN | lane F State 7, A9 | The disclosure line IS the access-locked UI; no separate "access denied" banner |
| 33 | `dispshort()` curated long-name abbreviation table + CSS ellipsis fallback for unlisted names | RETAIN | lane F State 9 | |
| 34 | Fold/show-more at the 3-row threshold, CSS-suppressed control below threshold; DOM-side `restoreFold()` reimplements the same threshold for the hydrate path | RETAIN | lane F State 10 | |
| 35 | Self-grader / Track Record (`#grader`, `engine.sector_central_grader`, nightly-sole-advancer, ledger NEVER read back into a live score) | RETAIN | lane D §6(a), A9 | Overview-mounted even though R2's grouping implied Explore; DOM home is Overview |

## The Map view

| # | Capability | Disposition | Dossier cite | Note |
|---|---|---|---|---|
| 36 | Rotation map SVG quadrant scatter (`#rvx-rmap`), context-labeled, no gated call | RETAIN | lane C §1 row 1 | |
| 37 | Rotation-map accessible text/table equivalent (`#rvx-board`, full ranked list) | RETAIN | lane C §1 row 1 | Reads the SAME `RVX_D` array as the chart |
| 38 | Linked-board `reco` tag rendering (`enter/accumulate/hold/trim/avoid` → Buy/Add/Hold/Trim/Avoid) | RETAIN | lane C §1 row 2, A3 | **CONFLICT (context surface rendering action vocabulary)** — recorded, flagged, NOT repaired this wave; brief forbids amplifying this into action-lane authority |
| 39 | Sector-cycle clock chart (`#sc-chart`, lazy-mounted `@cycles`) | RETAIN | lane C §1 row 3 | GAP: no accessible text equivalent located for this specific chart; GAP: intraday-vs-nightly cadence unconfirmed. Design brief requires an accessible equivalent be added in R3. |
| 40 | "One gated read per sector" board (`#board`, 11 GICS SPDRs, engine.sector_central conviction chain) | RETAIN | lane C §1 row 4 | GAP: render-function field binding not traced |
| 41 | `si-read-map` strip (`readMap()`, same `theme_intel.themes` source as the board) | RETAIN | lane C §1 | |
| 42 | Map-view context disclaimer copy ("Only the lanes above carry a gated, graded call") | RETAIN | lane C §1, A3 | This is the disclaimer the reco tags render BENEATH — same defect class as A3 |

## The Moving view

| # | Capability | Disposition | Dossier cite | Note |
|---|---|---|---|---|
| 43 | `si-read-moving` strip (counts up/down movers from `pulse_rank_delta_5d` sign only) | RETAIN | lane C §2 row 1 | Explicit "ranks nothing, gates nothing" receipt text |
| 44 | Rotation-events / flow-lane board (`#rc-events-mount`) | RETAIN | lane C §2 row 2 | GAP: no table alternative confirmed beyond the rendered board itself |
| 45 | Whole-market rotation map (`#rotation-app`, 269 subsectors + Mag-7 composite) with `drawStrip()`/`drawTrackRecord()` text accessible equivalents | RETAIN | lane C §2 row 3 | GAP: upstream Finviz snapshot refresh cadence unconfirmed |
| 46 | Desk-watch panel (`#desk-watch-mount`, turn desk + tape-onset, both DISPLAY-ONLY by producer docstring) | RETAIN | lane C §2 row 4 | Explicit quiet-tape sentence when nothing flagged |
| 47 | Moving's canonical binding = five nightly artifacts (`rotation_events.json`, `sector_fragmentation.json`, `subsector_rotation.json`, `oracle_turn_desk.json`, `oracle_tape_onset.json`) — NOT `si_handoff.json` | RETAIN | lane C §2a, A2 | Handoff-presupposition REFUTED by code; see README A2 note |

## The Money view

| # | Capability | Disposition | Dossier cite | Note |
|---|---|---|---|---|
| 48 | `si-read-money` strip (`data-regime` attribute, baked server-side from `si_handoff.json` `flow.cluster.regime`) | RETAIN | lane C §3 row 1, A2 | The ONE in-scope-view field that binds to `si_handoff.json` per A2 |
| 49 | Money-flow verdict card (server `flow.cluster.regime` headline + client `etf_pulse.json`/`vol_sentiment.json` chips) | RETAIN | lane C §3 row 2 | GAP: chip renderers not traced field-by-field |
| 50 | Market breadth gcards (`#mkt-breadth` etc., `theme_intel.market_concentration`, per-field null guards) | RETAIN | lane C §3 row 3 | GAP: exact `engine.*` module not isolated |
| 51 | Sector-ETF flow board table (`#sc-flows`, server-rendered, display-only) | RETAIN | lane C §3 row 4 | Whole section omitted (no placeholder) when `flows_html` is `None` |
| 52 | Market-heat treemap (`#heatmap-scorecard`) with client polling on `generated_utc` change | RETAIN | lane C §3 row 5 | The one live/intraday-polling clock among Map/Moving/Money; absolute-stamp comparison, not a baked delta — does NOT fall into the freshness-delta trap |
| 53 | Index-leadership strip (`#scc-leadership`) with self-graded "Validated / Measuring / Accruing" sub-line | RETAIN | lane C §3 row 6 | GAP: writer cadence not independently confirmed beyond in-template citation |

## The Explore view

| # | Capability | Disposition | Dossier cite | Note |
|---|---|---|---|---|
| 54 | Client-side filter/sort controls (mode tabs, category chips, column sort, chart range picker) with `localStorage` persistence, no server round-trip | RETAIN | lane D §1 | No free-text search box exists (confirmed absent, not a gap) |
| 55 | Full basket table (`#btable`): name, optional Group-pulse, sparkline, 1d/5d/20d/60d/MTD/YTD, synthetic S&P 500 benchmark row | RETAIN | lane D §2 | |
| 56 | Default 20d-descending sort; top-8/bottom-8 render with "Show all" revealing all 49 baskets | RETAIN | lane D §2 | Explore table does NOT read `window.SECTOR_CENTRAL` — client fetch of `baskets.json` only |
| 57 | Performance chart (`lightweight-charts`, rebased to 0% at window start, deferred-mount fix for `display:none` 0px-width bug) | RETAIN | lane D §3 | No `<table>`-only fallback / `aria-label` summary found — design brief requires one |
| 58 | Time Machine (`#tm-mount`, replay of measured history, unit/year/preset controls, "no predictive claim") | RETAIN | lane D §4 | Producer runs OFF the 67-min render path (separately scheduled) |
| 59 | Forming Narratives deterministic score + 5-leg breakdown (fixed-weight formula, no LLM) | RETAIN | lane D §5, A8 | |
| 60 | Forming Narratives `ai_watch` field — LLM-sourced (DeepSeek via `engine.master_brain._call_model`), printed verbatim, feeds no score/rank/gate | RETAIN | lane D §5, A8 | Binding matrix and brief MUST label this "model analysis"; the deterministic rank is NOT so labeled |
| 61 | Forming Narratives standing caveat text (non-predictive disclosure, conditional caveats) | RETAIN | lane D §5 | |
| 62 | Falsifier-register label rewrite at read time ("Kill criterion: X" → "Watching for: X") | RETAIN | lane D §5 | 2026-07-27 operator ruling #3821, upheld by house law |

## The Confluence view

| # | Capability | Disposition | Dossier cite | Note |
|---|---|---|---|---|
| 63 | Four independent universe artifacts (S&P/Baskets/Nasdaq/Russell), one shared render engine, structurally no client-side mixing | RETAIN | lane E §0 | |
| 64 | Tab order: hard-coded DOM order S&P → Nasdaq → Russell → Baskets | RETAIN | lane E, A4 | DAC-005's drift claim REFUTED — conflated `DS` JS declaration order with tab order |
| 65 | S&P thin-but-listed wording (`n_gateable`/`n_subsectors`/`n_thin`) | RETAIN | lane E §4, A5 | Wording is semantically INACCURATE for the 48 gate-dropped groups (they are not "listed in the table") — recorded, not repaired this wave |
| 66 | Baskets-tab thin/gateable disclosure | **BLOCKED_DATA** | lane E §4, A5, capability priors | `basket_confluence.json` coverage carries only `n_baskets`; no gateable/thin fields exist to disclose |
| 67 | Nasdaq/Russell thin-but-listed wording (code-shared with S&P, currently silent at `n_thin=0`) | RETAIN | lane E §4, A5 | GAP: nonzero-`n_thin` branch never observed live for these two universes |
| 68 | State/regime label vocabulary (`_STATE_META`, 9 states, EN/ZH) shared across all four universes | RETAIN | lane E §5 | |
| 69 | Coarse class/ribbon buckets (`entry_now/forming/tailwind/neutral/late/headwind`); `forming` has no ribbon bucket and folds into Neutral | RETAIN | lane E §5 | |
| 70 | S&P row identity + producer sort order (`_slug(sub_industry_name)`, `kind="subsector"`, `_CLASS_ORDER` tuple) | RETAIN | lane E §6 | Pinned detector, see §7 below |
| 71 | Full-table client-side re-sort (default tier-ascending; independent of, and can diverge visually from, producer class/weight/rs60 order) | RETAIN | lane E §6 | |
| 72 | Basket rows: `basket_id` stamp + `b-` filename-prefix disambiguation (same `subsector/` directory as S&P) | RETAIN | lane E §6-7 | |
| 73 | Nasdaq/Russell amalgamation rows (`kind="sector"`, `amalg-` id prefix, always `with_members=True`) | RETAIN | lane E §6, §8 | |
| 74 | Per-universe group detail pages (`subsector_detail.html.j2`, separate directories for Nasdaq/Russell) | RETAIN | lane E §7 | |
| 75 | Members-listing sort (own-cascade weight desc, tie-break `vs_basket` desc) | RETAIN | lane E §8 | |
| 76 | Stock detail destination (`stockHref`, uniform `stock.html#<TICKER>` across all four universes) | RETAIN | lane E §9 | |
| 77 | Coverage wording template (verbatim EN/ZH, per-universe noun swap) | RETAIN | lane E §10 | |
| 78 | S&P row-identity detector for a foreign/theme row (5-part rule: `kind`, no `basket_id`, `_industry_map()` traceable label, `universe=="sp500_subsectors"`, producer-only attack surface) | RETAIN | lane E §7 | This is the mechanism the attack test pins (Deliverable 9) |
| 79 | Confluence full-table search has NO "no results" message on zero matches (count-only `0/N` header) | RETAIN | lane F State 3 | Genuine production absence in the OPPOSITE direction of the R2 candidate's fabricated placeholder (PRC-007) — production must not gain an invented message; not a BLOCKED_DATA case (no field is missing, the UI copy simply was never written) |

## Cross-cutting: routing contract (Deliverable 4 detail)

| # | Capability | Disposition | Dossier cite | Note |
|---|---|---|---|---|
| 80 | Six canonical views + `VIEWS` array, exact-match hash dispatch | RETAIN | lane B §1-2 | |
| 81 | 21-entry `LEGACY_ANCHORS` table | RETAIN | lane B §3 | PRC-003's "collapses/drops" claim REFUTED against production — all four named hashes present and mapped |
| 82 | `#theme-*` boot-time-only redirect via `resolveThemeHash()` | RETAIN | lane B §4, A7 | Seam recorded (only the FIRST page-load hash redirects; a later in-page `#theme-*` hashchange just shows Overview) — filed separately, not repaired |
| 83 | `#read-*` trace-open with defer/retry (`pendingTrace`, held until the Act-Now board exists) | RETAIN | lane B §5 | |
| 84 | Unknown/empty-hash fallback to Overview + `replaceState('#overview')` on empty hash | RETAIN | lane B §6 | |
| 85 | Deep-link scroll mechanics: `scrollIntoView({block:'start'})`, no `behavior` key (defaults instant, not smooth) | RETAIN | lane B §7 | Known automation-pane smooth-scroll trap does NOT apply to this call |
| 86 | Per-view working-destination inventory (Overview/Map/Moving/Money/Explore/Confluence hrefs, static + runtime-generated) | RETAIN | lane B §8 | |

## Cross-cutting: access/hydration contract (Deliverable 5 detail)

| # | Capability | Disposition | Dossier cite | Note |
|---|---|---|---|---|
| 87 | Single premium wall = `premiumdata/sector_central.json`, gating ONLY the Overview Act-Now board | RETAIN | A9, lane A §8, lane D §8 | |
| 88 | Explore/Confluence/Map/Moving/Money payloads all ungated | RETAIN | A9, lane D §8, lane E GAP | Explore/Confluence not exhaustively HTTP-verified — inference from `config/site_access.yml`, not a live curl |
| 89 | Nightly-sole-advancer rule for the Track Record ledger (`engine.ledger_lane.nightly_advance_enabled()`) | RETAIN | A9, lane D §6(a) | |
| 90 | Loading state: baked HTML for Overview (no skeleton); Confluence's `#sc-app` pre-`render()` static shell (no skeleton) | RETAIN | lane F State 1 | Transient/timing state, not a distinct payload shape |
| 91 | Cardinality-extreme capping with count-labeled controls (Overview lanes cap 3; Confluence caps 4/8/12) | RETAIN | lane F State 10 | |
| 92 | Correction/revision representation (a value later corrected/restated) | **BLOCKED_DATA** | lane F State 8, A6, capability priors | No code path in any file read renders a correction/revision marker; no producer contract exists to mirror. Brief instructs R3 NOT to invent a correction affordance without a producer. |

---

## Disposition summary

- **RETAIN**: 90 of 92 capabilities inventoried.
- **BLOCKED_DATA**: 2 — Baskets-tab gateable/thin disclosure (#66), correction/revision representation (#92). Both per ADJUDICATIONS §"Capability ledger priors", both because the producer emits no field to disclose, not because of a design choice.
- **IMPROVE / REMOVE / RELOCATE**: 0, per ADJUDICATIONS: "Nothing in this wave is REMOVE or RELOCATE. Any candidate for those requires a new ruling here first — no implicit deletion." No IMPROVE disposition was invented for recorded-but-unrepaired defects (A3, A6, A7 seams); those stay attached to their RETAIN capability as a note, since the capability itself ships today and its repair is a separately filed, out-of-scope item.
