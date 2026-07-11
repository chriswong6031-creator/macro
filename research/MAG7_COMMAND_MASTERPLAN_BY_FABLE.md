# Mag 7 Command — mega-cap regime, leadership rotation, and tech fragmentation

Status: ADJUDICATED MASTERPLAN (Fable, 2026-07-11). Operator-initiated: "MAG 7 is on the
run … yet our us_stocks.html and baskets.html dashboard does not reflect any of this."

## 0. The incident of record (what the operator saw vs what the site showed)

Verified from our own stores (data/baskets/ohlcv through 07-08; massive_stock_day through
07-02; live tape through 07-10 per operator):

- MAGS (Roundhill Mag-7 ETF): $61.60 on 06-26 → $65.10 by 07-02 (+5.7% in 4 sessions)
  → ~$67 by 07-10 (+~9%). SPY +2.2%, SMH **−3.2%** over the same start window.
- Members since 06-26 (through 07-08): AAPL +10.4%, META +9.6%, GOOGL +7.3%, AVGO +6.5%,
  NVDA +6.0%, AMZN +4.7%, TSLA +3.8%, MSFT +2.8%. Last-2-days leadership had rotated to
  NVDA (+4.4%) / AVGO (+4.0%); META led 07-09/07-10 per operator.
- Memory/HBM crashed while the generals ran: since 06-26 MU −16.2%, SNDK −17.4%, WDC −6.2%,
  STX −4.4% — after a multi-month melt-up during which NVDA was flat (memory_storage still
  ranks #1/46 on the allocation page's 13-6-12-1w momentum while −17% in 10 sessions).
- MAGS is still ~8% below its 52-week high: the run is a **recovery inside a larger
  consolidation** — which is exactly why every trend-anchored engine read it as a bounce.

What the site showed on 07-11: mag7 basket labeled **deteriorating → avoid** (action-board
avoid lane), ignition radar headline **⚪ OFF · K=0/8** (its own narrow channel
simultaneously scoring Magnificent Seven 0.70, "igniting"), Size & Style calling the regime
"mega-cap-led — narrowing" as a *warning*, NVDA appearing only as "UNCONFIRMED TURN" in
holdings, and page data frozen at as_of 07-09.

### Root causes (three independent layers)

**L1 — Ops.** The 07-11 nightly `collect` job was **cancelled at its timeout**
(05:15:16→06:55:33, exactly 100 min; conclusion=cancelled so no alert fired — the known
silent class). The `engine` job then ran green on stale stores → page as_of 07-09,
missing the two strongest sessions. 07-08 and 07-09 nightlies were outright failures.

**L2 — Structural suppression.** Six independent mechanisms each hide a cap-weighted
mega-cap run (census 2026-07-11, sonnet lanes, verified first-hand):
1. `engine/theme_scoring.py` `_label()`: equal-weight `pct50 < 0.4` trips "breaking" —
   on a 7-member basket one stock's 50dma cross moves breadth by 14pp; 2/7 = 0.286.
2. `_label()`: `r20_rel < 0 AND breaking → deteriorating` — mag7 r20_rel was −0.26%
   (the 20d window straddles the 06-26 run start; the run sits in the denominator half).
3. `_reco()`: `deteriorating → avoid`, deterministic, no disclosure of a split tape.
4. `engine/baskets.py` HORIZONS = {1d,5d,20d,60d}: no 10d window; a 15-day run falls
   between the rulers. (MTD catches it but is neither sort key nor scoring input.)
5. `engine/ignition_radar.py`: broad chips go stale at `_FRESH_BD = 10` business days →
   headline OFF **because** the regime persisted; the accurate narrow regime label is
   demoted to a glance line under the OFF badge.
6. No cap-weight lens exists anywhere: no CW basket track, MAGS collected (in
   `massive_stock_day`) but wired into nothing, mega-cap dominance surfaced only as a
   fragility warning (Size & Style / breadth divergence).

**L3 — Conceptual gap** (census of all existing organs): nothing computes (a) a Mag-7
cohort bull/bear regime state, (b) "which general leads now" rotation, (c) intra-cohort
fragmentation display, (d) any "Mag 7 is running" surface. Adjacent organs exist and are
consumed, not duplicated (§2).

## 1. Doctrine position

Everything below is **display/context tier** — ships freely under the promotion-gate law;
no authority, no rank/size/gate. The regime ledger accrues from day 1 (context-accrual
law); any promotion is a separate pre-registered study at a pre-declared horizon ruler
(clock §6). The `deteriorating→avoid` channel in theme_scoring is the **backtested
drawdown channel** (27y SPDR-sector proxy) and is NOT touched (M7C-R4). LLMs originate
nothing here; all states are deterministic price/breadth arithmetic.

## 2. Boundary map (consume, don't duplicate)

| Existing organ | Owns | Mag 7 Command consumes |
|---|---|---|
| Leader Radar (ACTIVE) | per-name lifecycle over ~150-190 names; market-wide leadership_regime chip (LR-R5, radar-page-resident) | member lifecycle states as chips (later; fail-open) |
| Ratio Lens (ACTIVE, W2 pending) | pairwise ratio state machines (mag7_vs_ailogic, qqq_vs_rsp, memory_vs_ailogic); MAGS/SMH as traded refs | nothing yet; panel links to ratio_lens.html when live. We build NO pairwise ratio math (M7C-R5) |
| nasdaq_internals | archetype groups incl. megacap_quality (8 names w/ AVGO), group RS/dispersion | nothing (different universe cut); crosswalk noted in Tier-2 receipt |
| mtf_upturn (TS-R7) | per-member UPTURN states + Mag7 transition alert | member `mtf` chip in the panel table |
| Oracle panel | cohesion/breadth/turnover per node (2021+) | future Tier-2 receipt only |
| basket_turn_watch / ignition narrow | turn & ignition state for the mag7 *basket* | shown unchanged; we add persistence honesty (M7C-R7) |
| Haven audition (report) | AAPL shelter/exit-trap, META asymmetry (qualitative) | cross-link only |

DO_NOT_REBUILD compliance: no rs-dispersion **gates** (display only); no shock→archetype
map; no per-ticker business-model tags (price data only); no positioning fusion; nothing
here re-tests a killed construction. No kill-registry append needed (nothing killed).

## 3. Rulings

- **M7C-R1 (gap ruling).** The Mag-7 *cohort* regime organ is a distinct build: aggregate
  state over exactly the 7 names, cap-weighted, with leadership attribution. Per-name
  lifecycle (Leader Radar), pairwise ratios (Ratio Lens), and market-wide breadth organs
  remain the owners of their lenses; boundaries per §2 table.
- **M7C-R2 (construction).** Cap-weighted composite from member closes ×
  latest weekly-committed Polygon reference mktcaps (renormalized; the heatmap's reference
  store). MAGS is a **traded reference display only** — its store (`massive_stock_day`)
  lags; it never enters computation. If mktcap reference is unavailable → fall back to
  equal-weight WITH a visible disclosure flag.
- **M7C-R3 (two-axis state, display-tier).** trend_state ∈ {running_broad, running_narrow,
  turning_up, cooling, rolling_over, down} × structure ∈ {at_highs, recovering, drawdown}.
  Pre-declared arithmetic (§4). A run inside a drawdown reads "Running — narrow · still
  8% below the May high", not OFF and not AVOID. Nightly is the sole ledger advancer.
- **M7C-R4 (validated-channel preservation).** `_label()`/`_reco()` semantics untouched.
  The 27y calibration domain is sector-scale baskets; a 7-member basket's pct50 is
  quantized in 1/7 steps and out-of-domain — but the remedy is **disclosure, not gate
  surgery**: theme_scoring emits additive `leadership_split` display fields (§4, PR-E).
  Any gate change is a separate operator-ratified prereg.
- **M7C-R5 (fragmentation lens).** The "tech legs" strip shows each leg's OWN tape
  (10d/20d rel + plain word) for mag7(CW) / AI chips / memory / software from existing
  basket perf. No pairwise ratio math (Ratio Lens owns it), no dispersion gates
  (rs-dispersion DON'T-TEST honored), descriptive only.
- **M7C-R6 (doctrine).** All copy per docs/DESIGN_DOCTRINE.md: fixed stance vocabulary,
  banned Tier-1 words, hard budgets, bilingual parity, mockups-first with screenshots,
  browser-verify on prod-shaped data. Internal state slugs never render on Tier 1.
- **M7C-R7 (ignition persistence honesty).** Display amendment to the ignition card: when
  the narrow channel's top theme has persisted N sessions, the headline row carries
  "running · day N" alongside the broad state instead of letting ⚪ OFF dominate a live
  regime. No gate/threshold changes; chips stay honest about staleness.
- **M7C-R8 (ops).** Raise the `daily.yml` collect timeout (died at exactly 100m) with
  headroom + make an engine run on a stale basket store LOUD (the #1917 freshness gate
  covers SPY/regime lanes; the basket ohlcv path ran green on stale data — extend
  coverage or emit an explicit ::warning + alert). Root cause documented in the PR.
- **M7C-R9 (field guide first).** Mag-7 cycle behavior gets a descriptive field guide
  (episode census: every CW-composite run ≥ +8%/≤30 sessions, its breadth shape, who led,
  what semis/memory/software/SPX did, how it ended) BEFORE any backtest ruler exists
  (understanding-before-backtest law). Rulers derive from the playbook later.
- **M7C-R10 (no new collector).** MAGS already lands in `massive_stock_day`; read-only
  wiring; if its last bar is > 5 sessions stale, hide the reference quote (fail-open).
- **M7C-R11 (naming).** User-facing: "Mag 7" / 「七巨头」. Internal: `mag7_regime.v1`.
- **M7C-R12 (page-order).** The panel lives on us_stocks near the top (with ignition
  radar), and baskets.html gets only the split-tape chip + leaders line on the mag7 row —
  baskets' 20d-rel sort semantics are NOT changed in this program.

## 4. Engine spec — `engine/mag7_regime.py` (mag7_regime.v1)

Inputs: member closes (`data/baskets/ohlcv/*.parquet`), SPY (same store family the
builders already use), Polygon mktcap reference, MAGS (`data/massive_stock_day/MAGS.parquet`),
`site/stockdata/mtf_upturn.json` (fail-open).

Computed (all windows in trading sessions):
- CW + EW daily return composites (weights = latest mktcap, renormalized, logged in artifact).
- Member table: r2/r5/r10/r20, rs20 vs SPY, above 50/200dma, contrib10 (weight×return
  share of CW 10d move), mtf state.
- k7_trend = #above 50dma; k7_rs = #rs20 > 0.
- up := (cw_r10 ≥ +2%) AND (CW > its 20dma).
- trend_state precedence:
  - `turning_up`: up AND the up-condition was false 10 sessions ago AND first true within
    the last 5 sessions.
  - `running_broad`: up AND k7_trend ≥ 5. `running_narrow`: up AND k7_trend ≤ 4.
  - `rolling_over`: cw_r10 ≤ −2% AND CW < 20dma AND up was true within the last 20 sessions.
  - `down`: CW < 200dma AND dd ≤ −15% AND NOT up.
  - else `cooling`.
- structure: dd = CW vs 252-session high. `at_highs` dd ≥ −3%; `recovering` −15% < dd < −3%
  AND cw_r20 > 0; else `drawdown`.
- run meter: start = first session of the current consecutive CW>20dma streak; sessions,
  cw return since start, SPY return since start.
- generals: members sorted by contrib10; smallest prefix covering ≥60% of positive
  contributions, cap 3. `joining`: top-2 contrib2 members not already generals.
- spread20 = max−min member r20 (plain "gap between best and worst").
- tech_legs: for [mag7(CW), ai_semiconductors, memory_storage, ai_software] r10/r20 rel
  SPY from existing basket perf; word map: r10_rel ≥ +5% "surging", ≥ +2% "running",
  ≤ −5% "falling hard", ≤ −2% "falling", else "flat".
- Ledger: `data/mag7_regime/ledger.jsonl` append {date, trend_state, structure, k7,
  cw_r10, generals} — one row per session, nightly only.
- Artifact: `data/mag7_regime/latest.json` (+ published copy `site/stockdata/mag7_regime.json`),
  wired via `engine/run.py` exactly like ignition_radar; synapse.yml registration + DAG
  step declaration required.

## 5. Waves / PR lanes (all same-day; file-disjoint except noted)

| PR | Lane | Contents |
|---|---|---|
| A | ops | daily.yml collect timeout raise + stale-basket-store loud warning; root-cause note (M7C-R8) |
| B | docs | this masterplan |
| C | engine | mag7_regime.v1 + engine/run.py wiring + synapse/DAG reg + tests (ci.yml whitelist) |
| D | surfaces | us_stocks "Mag 7" panel + tech-legs strip; baskets mag7 split-tape chip + leaders line; mockups-first; consumes C artifact + E fields, fail-open on both; merges last |
| E | scoring fields | theme_scoring additive `leadership_split`/`leaders` display fields (M7C-R4); `10d` added to HORIZONS (additive; consumers verified) |
| F | ignition honesty | narrow-persistence display fields + card copy (M7C-R7) |
| G | research | MAG7_FIELD_GUIDE.md episode census (M7C-R9) |

Panel glance contract (D): title "Mag 7"; state line ≤14 words ("Running — narrow ·
day 11 · +9% since Jun 26 vs S&P +2%"); stance from the fixed vocabulary
(running_narrow → "In favour — watch, don't chase"; turning_up → "Get ready";
rolling_over → "Protect gains"; down → "Stand aside"; cooling → "Watch — no rush");
7-dot member bar; "Led by Apple + Meta — Nvidia joining" line; structure chip; tech-legs
strip ("Mag 7 ▲▲ · AI chips ▲ · Memory ▼▼ · Software —"); ONE footer ("Cap-weighted view
of the 7 largest US stocks — the Buy lanes below still decide entries."); receipts,
member table, weights basis, MAGS quote + as-of, and the EW-vs-CW method note on hover.

## 6. Clocks

- 2026-07-14: verify first nightly artifact + ledger row; verify collect ran to completion.
- 2026-08-15: first regime-ledger read (descriptive; states vs subsequent 10/20d tape).
- 2026-10-15: promotion decision — whether any mag7_regime state earns a prereg at a
  declared horizon ruler; display tier continues regardless (null never blocks accrual).
