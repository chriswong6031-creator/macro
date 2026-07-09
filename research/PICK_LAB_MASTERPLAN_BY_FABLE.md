# Pick Lab — candidate stock-pick engines on forward entry ledgers (masterplan by Fable)

Date: 2026-07-09 · Status: ADJUDICATED — build authorized (display-tier)
Program id: `pick_lab` · Operator directive: 2026-07-09 session (us_stocks pick-engine upgrade)

---

## §1 Problem statement and diagnosis

The operator's complaint: the flagship us_stocks board gates entries on the 2D/3D
RSI-MACD × StochRSI confluence cascade (T1–T4, `engine/confluence_tiers.py`), which is
*correct as a risk gate* but structurally late on fast movers — names whose 1D grid
crossed and ran never print a 2D/3D confluence until they are unchaseable.

As-built facts (verified 2026-07-09, engine census):

- The oscillators are **RSI-MACD** (EMA14−EMA60 of RSI14, signal EMA5) — the "cross" is a
  signal-line cross, not a 20/80 level cross. The 20/80 lines apply **only to StochRSI D**:
  `d < 20 within 8 bars` = "deep/from-oversold" confirmation (`fromos`), `k or d ≥ 80` =
  overbought **veto** (`not_topped=False` blocks all buy tiers).
- Grids: 1D (raw daily), 2D (`resample("2B")`), 3D (`resample("3B")` — master), weekly
  (confirm channel). T1 = 3D×3D endorsed; T2 = 2D MACD cross + recent 3D StochRSI;
  T3/T4 = projected 2D crosses (already an "early" concession, weights 0.6/0.4).
- #1701 (T1–T4 deep-dive): entry-quality score **anti-correlates** with forward return
  (rank-corr −0.05..−0.14) — the gate buys risk control (MAE/drawdown), not return. This
  directly supports the hypothesis that the gate's speed cost is real and measurable.
- There is **no challenger pick engine** in production. `gate_go` is NEUTRAL; the board
  ranks by bottoming-alignment with Conviction as display.

The fix is not to loosen the flagship. It is to run **many small, frozen, first-principles
candidate books in parallel on honest forward ledgers** ("shadow books"), measure them
against controls, and let evidence (plus operator daily review) pick which constructions
earn a gauntlet slot.

## §2 Rulings (PL-R1..R12)

- **PL-R1 (tier).** The lab is display-tier. It ranks and gates NOTHING in production
  (NW-ART2 perimeter). Promotion of any book beyond display requires the existing
  gauntlet, including a time-preserving placebo (RC-RUL-3/5 law). Building and accruing
  is free (gauntlet = promotion gate, not build gate).
- **PL-R2 (frozen configs).** Every book registers `engine_id`, frozen config, and
  `config_hash` at ship time. Any parameter change ships as `engine_id`-v2 with a fresh
  ledger; ledgers are never edited or re-scored in place.
- **PL-R3 (rulers, pre-declared per family).** Momentum/quality/1D/flagship-variant
  books: primary ruler = **21-trading-day SPY-excess** (WR + median excess), 5/10/63d
  recorded as descriptive ladder. Washout/reversion family: primary ruler = **21-session
  absolute reversion-capture** + MFE/MAE asymmetry (oracle-reversion convention, #1458 —
  63d excess apparatus is the wrong ruler there). Inverse/avoid book: 21d SPY-excess,
  scored as avoid-accuracy (expected negative). Long-hold grids: **126d and 252d
  sector-relative + SPY-excess, descriptive only** (horizon ladder law: verdicts only at
  the pre-declared `horizon_role` ruler).
- **PL-R4 (n discipline).** Effective N = distinct fire-date clusters, not rows. Books
  enforce a **no-refire-while-open** rule (a ticker cannot re-fire in a book within 21
  sessions of its last fire; 63 sessions for LH grids). No verdict language before
  n≥25 fires spanning ≥3 calendar months and ≥6 distinct fire dates; until then the UI
  badge is **ACCRUING**. Even past the floor, the page prints *descriptive* summaries
  only (no "validated" — CI-enforced word).
- **PL-R5 (controls are mandatory).** `plab_random_ctrl` (deterministic random book) and
  the universe buy-anytime base rate are scoreboard columns; every book's headline
  number is **lift over both**, not raw WR.
- **PL-R6 (long-hold firewall).** LH grids carry `horizon_role: hold_thesis`, live in
  separate artifacts (`data/pick_lab/lh_*.jsonl`, `site/labdata/pick_lab_longhold.json`),
  and are never consumed by entry surfaces (LH-R1, CI-enforced). Promotion machinery for
  long-hold belongs to the long-hold program (G1), not this lab. The lab contributes
  forward evidence only.
- **PL-R7 (PIT by construction).** Candidates read exactly one input: the frozen nightly
  **universe snapshot of record**. It is assembled in two deterministic same-night steps:
  (a) the core produced by `build_stock_library` at score time (scores, oscillators,
  technicals, washout, tier), and (b) a sector/regime **enrichment join** performed by
  the lab runner from that same night's committed artifacts (sector phase/stage/bucket,
  calm/stress/liquidity) — the enriched frame is persisted as the snapshot of record and
  is the only thing candidates see. No candidate may read any other artifact at fire
  time. Both steps are additive and never-fatal (a snapshot failure must not break the
  render).
- **PL-R8 (operator review).** Daily anecdotal review of book picks is a sanctioned
  *selection heuristic* for which constructions earn gauntlet slots — never promotion
  evidence by itself.
- **PL-R9 (kill adjacency).** Books 8 and 13 are constructions *adjacent* to standing
  kills (near-52w-high anti-signal in MEASUREMENT_FLOOR; insider×T2 KILLED #1781). They
  are permitted as **new constructions** under the construction-specific-kill law, and
  their registry rows cite the kills. Book 19 measures the veto/exit side; it does not
  re-propose FRESH-BUY-as-edge (REFUTED #1513). Book 10 is a sector-*phase* screen, not
  the killed oracle-rotation×cycle-position confluence — the registry row states this.
- **PL-R10 (ledger law).** Nightly is the sole advancer (HOUSE-U5). `build_pick_lab` is
  idempotent per as_of (keep-first dedup); intraday runs discard writes. All rows carry
  `authority: "display_only"`.
- **PL-R11 (headline hypothesis).** The 1D-velocity family (books 1–4) plus ablations
  (17, 18) exist to price the flagship gate's speed cost. First operator read clock:
  **2026-08-20** (~30 trading days of accrual). Nothing is decided before it.
- **PL-R12 (determinism).** No LLM output anywhere in candidate logic, ledgers, or
  scoring. All functions deterministic; the random book seeds from
  `sha256(engine_id + asof)`.

## §3 Candidate registry (20 entry books + 3 long-hold grids)

All entry books: max 12 picks/day, ranked; liquidity floor `close ≥ $5` and
`dollar_adv_20d ≥ $10M` (rows missing adv pass with `liq_unknown` flag); dedup
no-refire-while-open 21 sessions. "quartile/decile" = within that day's snapshot universe.

### Family A — 1D velocity (operator thesis; ruler: 21d SPY-excess)

| # | engine_id | Construction (frozen v1) | Rank by |
|---|---|---|---|
| 1 | `plab_1d_pure` | 1D RSI-MACD cross-up ≤2 sessions ago AND 1D StochRSI k×d cross-up ≤8 sessions AND 1D `from_os` (d<20 within 8) AND rsi14<65 | composite_z |
| 2 | `plab_1d_regime` | 1D MACD cross ≤2 AND 1D k×d cross ≤8 AND calm≥0.5 AND liquidity≠contracting AND ext_grade≠parabolic (no RSI cap, no from_os — admits strong names) | edge_alpha |
| 3 | `plab_1d_sectorheat` | book-2 base conditions AND [(sector_stage∈{improving,leading} AND sector_rs_mom20>0) OR sector_phase∈{Trough,Recovery}] | composite_z |
| 4 | `plab_1d_blastoff` | 1D MACD cross ≤3 AND 3D MACD **not yet** crossed (the exact cohort the 2D/3D gate misses) AND above_200 AND ext_grade=none | edge_alpha |

### Family B — momentum/continuation (ruler: 21d SPY-excess)

| 5 | `plab_breakout_vol` | close = 20d high AND vol_ratio_20d≥1.5 AND ext_grade≠parabolic AND calm≥0.5 | vol_ratio_20d |
| 6 | `plab_resid_mom` | calm≥0.5; top-12 edge_alpha; ext_grade≠parabolic; **no oscillator condition** (prices the gate's cost on momentum leaders) | edge_alpha |
| 7 | `plab_otr_pullback` | sector_bucket=on_the_run AND above_200 AND pct_vs_20dma∈[−8%,−2%] AND 1D k>d AND 1D d<50 (first pullback in a running sector) | composite_z |
| 8 | `plab_hi_base` | off_52w_high_pct≤10 AND vol_squeeze on (basing/coil) — kill-adjacent: near-52w-high alone is anti-predictive; this tests the *conditioned* construction (PL-R9) | composite_z |

### Family C — washout/reversion (ruler: 21-session ABSOLUTE reversion-capture + MFE/MAE)

| 9 | `plab_washout_deep` | washout_active AND dd_pct>25 AND (coiled OR star) AND 3D from_os | dd_pct |
| 10 | `plab_sector_trough` | sector_phase∈{Trough,Recovery} AND tier∈{T1,T2} fresh (t_ticks≤2) — sector-PHASE screen, not rotation×cycle (PL-R9) | composite_z |
| 11 | `plab_washout_clean` | washout_active AND dd_pct>20 AND dilution_events_365d=0 AND (days_since_shelf>90 or null) AND (interest_coverage>2 or null) | axis_quality |

### Family D — EDGE/quality (ruler: 21d SPY-excess)

| 12 | `plab_edge_pure` | top-12 axis_selection; only exclusion = earnings blackout; **no entry gate** (prices the gate's cost on the best-selection names) | axis_selection |
| 13 | `plab_edge_1d` | axis_selection top-quartile AND 1D MACD cross ≤3 AND 1D k×d cross ≤8 — kill-adjacent to insider×T2 (different construction: composite EDGE × 1D grid; PL-R9) | axis_selection |
| 14 | `plab_quality_pullback` | axis_quality top-quartile AND archetype∈{quality_compounder,secular_growth} AND pct_vs_20dma<0 AND rsi14<55 AND above_200 | axis_quality |

### Family E — context/personality (ruler: 21d SPY-excess)

| 15 | `plab_beta_squeeze` | archetype=high_beta_momentum AND current_mode=squeeze AND calm≥0.5 (low-n expected; prints honest n) | edge_alpha |
| 16 | `plab_revision_accel` | edge_revision≥1.0 AND implied_upside_pct≥15 AND NOT is_blackout AND above_200 | edge_revision |

### Family F — flagship ablations + controls (ruler: 21d SPY-excess)

| 17 | `plab_flagship_nogate` | top-12 composite_z **ignoring the confluence gate** (cycle hard-block states still excluded — isolates the oscillator gate specifically) | composite_z |
| 18 | `plab_flagship_t3t4` | top-12 composite_z among tier∈{T1,T2,T3,T4} — early/projected tiers admitted at full standing (speed-vs-quality inside current architecture) | composite_z |
| 19 | `plab_topping_avoid` | **INVERSE book (avoid, not buys):** cycle_state∈{TOP WATCH,ROLLING OVER} OR (sector_bucket=take_profits AND rsi14>70). Scored as avoid-accuracy: expected NEGATIVE 21d excess | rsi14 desc |
| 20 | `plab_random_ctrl` | 12 uniform-random liquid names; seed sha256(engine_id+asof). The yardstick (PL-R5) | random |

### Long-hold grids (horizon_role=hold_thesis; ruler: 126/252d sector-relative + SPY-excess, DESCRIPTIVE; N=10/day; refire lockout 63 sessions)

| LH-1 | `plab_lh_compounder` | axis_quality top-decile AND archetype∈{quality_compounder,secular_growth} AND dilution_events_365d=0 |
| LH-2 | `plab_lh_edge_durability` | axis_selection top-decile AND axis_quality above median |
| LH-3 | `plab_lh_washout_survivor` | dd_pct>40 AND axis_quality above median AND interest_coverage>3 AND dilution_events_365d=0 |

First LH maturation ETA: ~2027-01 (126 trading days). The lab page prints this honestly.

## §4 Measurement law (schemas)

**Fires** — `data/pick_lab/fires.jsonl` (entry books) / `data/pick_lab/lh_fires.jsonl`
(LH grids). Append-only, keep-first dedup on `(engine_id, ticker, fire_date)`:

```
{engine_id, ticker, fire_date, exec_date,        # exec = next NYSE session after fire
 rank, close_at_fire, sector,
 regime_calm, regime_stress,                     # stamped AT fire_date
 config_hash, authority: "display_only"}
```

**Grades** — `data/pick_lab/grades.jsonl` / `lh_grades.jsonl` (qledger split pattern:
fires immutable, grades fill in). Key `(engine_id, ticker, fire_date, horizon)`:

```
{engine_id, ticker, fire_date, horizon,          # h ∈ {5,10,21,63} entry; {126,252} LH
 ret_abs, ret_excess_spy, ret_rel_sector,        # exec close → exec+h close
 mfe, mae,                                       # over 25 sessions from exec (entry books)
 matured: true, graded_at}
```

Grading gates: a row grades at horizon h only when exec + h sessions have FULLY elapsed;
MFE/MAE only when exec+25 has elapsed. Prices from the canonical price store; missing
ticker → grade skipped and counted in an honest `ungradeable` counter (never silently
dropped). SPY from the same store. Exec price = next-session **close** (conservative;
EOD-only data — no same-day fills, oracle-reversion convention).

**Scoreboard** (computed nightly, per book): n_fires, n_open, distinct fire dates,
months span, per-horizon WR (abs + excess), median excess, median MFE / median |MAE| and
asym ratio, cumulative equal-weight 21d-cohort NAV (excess), max drawdown of that NAV,
lift vs `plab_random_ctrl`, lift vs universe buy-anytime base rate, status
(ACCRUING until PL-R4 floor). LH books: per-horizon medians + ETA only.

## §5 Architecture

```
engine/pick_lab/
  __init__.py
  signals_1d.py      # 1D-grid RSI-MACD + StochRSI (reuses engine/signal_quality math on the daily grid)
  registry.py        # the 23 frozen candidate defs above + config_hash
  candidates.py      # pure functions: (snapshot_df, regime) -> ranked picks per book
  snapshot.py        # snapshot schema, reader, monthly-partition writer helpers
  ledger.py          # fires/grades JSONL io (keep-first; authority stamp)
  grade.py           # maturation pass (price store join, horizon gates)
  book.py            # scoreboard computation (NAV ladder, lifts, floors)
scripts/build_pick_lab.py      # nightly runner (never fails: always exit 0)
data/pick_lab/snapshots/<YYYY-MM>.parquet   # PIT universe snapshot, monthly partitions
data/pick_lab/fires.jsonl | grades.jsonl | lh_fires.jsonl | lh_grades.jsonl
site/labdata/pick_lab.json                  # horizon_role: entry
site/labdata/pick_lab_longhold.json         # horizon_role: hold_thesis
site/us_stocks_lab.html                     # rendered by build_pick_lab (off critical path)
```

**Snapshot producer** — additive block at the end of `scripts/build_stock_library.py`
(next to the existing shadow-book freeze; wrapped try/except, never fatal). One row per
ticker in the full scored universe. Sector phase/stage/bucket and regime scalars are NOT
in scope there — they are joined by the runner's enrichment step (PL-R7b) from the same
night's committed sector/regime artifacts, and the enriched frame is what gets persisted
to `data/pick_lab/snapshots/`. Columns (null-honest — missing feature = null, never
fabricated): identity (ticker, sector, close, dollar_adv_20d, vol_ratio_20d, is_20d_high,
pct_vs_20dma, above_200, off_52w_high_pct, rsi14, ext_grade); scores (composite_z, score,
axis_selection, axis_entry, axis_quality, edge_insider, edge_sue, edge_revision,
edge_alpha); oscillators per grid g∈{d1,d2,d3} (g_macd, g_sig, g_macd_xup_bars, g_k, g_d,
g_kd_xup_bars, g_from_os, g_ob) + weekly_bull; gate (tier, t_ticks, gate_state);
context (cycle_state, urgency, sector_phase, sector_stage, sector_rs_mom20,
sector_bucket, coiled, star, washout_active, dd_pct, vol_squeeze_state, archetype,
current_mode, implied_upside_pct, is_blackout, dilution_events_365d, days_since_shelf,
interest_coverage); top-level attrs (asof, calm, stress, liquidity_overlay, spy_close).
1D/2D oscillator values are computed in the producer from the close panel already in
memory (vectorized; must add <30s to the step). The snapshot is ALSO the replay
substrate: accrued snapshots let future candidate ideas be tested over history without
new plumbing (context-accrual doctrine).

**Nightly wiring** — `daily.yml` engine-render job, immediately after
`build_stock_board_v2` (the fail-safe zone): `run_py "pick lab (build_pick_lab)"
scripts.build_pick_lab`. Outputs covered by the existing `git add data/ site/` commit
step. The runner: load latest snapshot (no snapshot → log + exit 0 honest no-op) → run
23 candidates → append fires → grade matured → compute scoreboard → write both site
artifacts → render `us_stocks_lab.html`.

**Synapse registration** — three artifacts in `config/synapse.yml`: pick-lab snapshot
tape (infrastructure), pick-lab entry ledger/site artifact (`horizon_role: entry`),
pick-lab long-hold artifact (`horizon_role: hold_thesis`). Update count pins +
conformance fixtures in the same PR (known merge-race guard).

## §6 UI spec — `site/us_stocks_lab.html`

Standalone page (own `.j2`), WITH standard `.site-nav` + `theme.js` end-of-body include
(settings gear + MDXAuth law). Bilingual `l-en`/`l-zh` spans; tooltips via
`data-tip-en`/`data-tip-zh`; NEVER translated text in `title=`; the word "validated"
never appears. Entry: a `🧪 Lab` button in the us_stocks stocks-header panel
(`dashboard.html.j2`, `{% if mode == 'stocks' %}` block) linking to the page.

Tabs (`.tabbtn` + `data-tab` pattern, inline script — same as btc_strategy/discovery):

1. **Scoreboard** — all 20 entry books ranked by accrued 21d excess lift; columns per
   §4; ACCRUING badges; random-control row pinned as the yardstick; honest n columns.
2. **1D Velocity** (flagship-2, featured) — books 1–4 full pick cards (ticker, why-chips,
   osc readouts, conviction, sector state) + two stock-level lanes: **On the Run**
   (stocks in on_the_run sectors, book-7 context) and **Take Profits / Topping**
   (book-19 avoid list, clearly labeled NOT-buys).
3. **All Books** — book selector chips → per-book picks-today grid + recent graded fires
   (ticker, fire date, 21d excess where matured) so the operator can eyeball performance.
4. **Long-Hold Grid** — LH-1..3 current grids + first-maturation ETA banner; firewall
   note (display-only, never feeds entry surfaces).
5. **Method** — plain-language EN/ZH description of the measurement law (§4), the
   controls, the ACCRUING floor, and what would promote a book (gauntlet + placebo).

Every pick card carries deterministic why-chips derived from its book's frozen config
(e.g. `1D✚ MACD×K/D` `deep<20` `sector heating` `EDGE q1`). Page renders an honest empty
state before the first snapshot exists ("first accrual tonight").

## §7 Long-hold decision (operator delegated)

Decision: long-hold books are IN the lab but firewalled (PL-R6), graded only at their
own ladder (126/252d, sector-relative primary), descriptive-only, with maturation ETAs
printed. No backtest is attempted for them — multi-year-hold backtests over one regime
era would violate the era-split law and teach us little; forward grids + the existing
long-hold program (G1, W1 labels, Winner Autopsy) are the honest instruments. The lab's
LH grids give the long-hold program a live recommendation-shaped evidence stream it
currently lacks, without a new "thesis lobe" (KILLED as duplicate — this is ledger
accrual inside an existing program's ambit, not a new NW lobe).

## §8 Kill-registry adjacency (cited at registration)

| Book | Standing kill nearby | Why this construction is distinct |
|---|---|---|
| 8 | near_52w_high anti-predictive (MEASUREMENT_FLOOR) | conditioned on squeeze/basing, not raw proximity |
| 10 | rotation×cycle-position entry-confluence DON'T-TEST | sector-PHASE screen (sector_central), no oracle rotation input |
| 13 | insider×T2 KILLED (#1781) | composite EDGE axis × 1D grid ≠ insider × T2-tier interaction |
| 19 | FRESH BUY as buy edge REFUTED (#1513) | measures the veto/exit side (avoid-accuracy), proposes no buy edge |
| 12/17 | Entry-time thesis at 21d REFUTED 3-for-3 (RUL-18..29) | those tested insider/macro/positioning timing; these are gate ABLATIONS of an existing composite |

## §9 V1 ship notes (accepted gaps, printed not hidden)

- **Universe buy-anytime base rate is null in v1.** PL-R5's second control
  (`lift_vs_universe_base`) ships as an honest null (never a duplicate of the
  random-control lift). Follow-up: compute panel-median 21d excess across ALL snapshot
  tickers per fire-date directly from the close panel. Until then the random book is
  the sole yardstick.
- **Producer budget watch.** The snapshot producer adds a per-ticker 3D `signal_frame`
  pass + dd_pct loop inside `build_stock_library` (~20–30s at current universe size).
  The producer logs `pick_lab snapshot: N rows for ASOF (X.Xs)` — check the first
  nightly run; if >30s, dedupe against the gate's existing signal_frame computation.
- **sector_phase is null-honest in v1** (no committed per-sector cycle-phase artifact
  nightly): book 3 fires on its sector_stage/rs_mom20 arm only; book 10's phase clause
  never fires until the enrichment source exists.
- **Scoreboard ruler label**: the reversion family (books 9–11) is lifted on the
  absolute ruler in `book.py` (per PL-R3); the template's lift column relabel for that
  family is a pending polish item.

## §10 Clocks

- **2026-08-20** — first operator read of the 1D-velocity family + ablations (PL-R11).
  Nothing promoted; prune obviously-dead books (0-fire or degenerate) to v2 configs.
- **2026-10-09** — first floor-eligible verdict window for high-frequency books
  (if n≥25 across ≥3 months); candidates that look alive get gauntlet preregs.
- **~2027-01** — first LH grid maturations at 126d.
