# US Stocks + Baskets Engine Overhaul — Conviction × Entry-Timing × Backtest

**Status:** in progress (branch `claude/musing-hypatia-3ab8c7`).
**Mandate (user, 2026-06-20):** the standout-stock / "what to act on now" engine gives misleading
signals — high scores + "Buy Now" on names that just topped their daily cycle (HWM, OFG, EWBC) and
about to retrace; and it risks false-vetoing real leaders (NVDA-style) on naive extension. Mastermind
and the Opus Brain consume these signals and lose money. Rework holistically.

## Locked product decisions (user)
1. **Veto strength = Balanced.** Demote a leader from "Buy Now" only on a *confirmed* momentum
   down-cross **and** overbought RSI (or a higher-timeframe 3D/W down-cross). Allows strong-trend
   continuation; still catches the shallow top.
2. **Two distinct gauges.** A slow **CONVICTION** ("Own-It": leadership + quality + valuation-aware)
   and a separate **ENTRY-TIMING** ("Enter-Now": buy now / wait-for-pullback-to-$X / extended / avoid,
   with timing + price). Never collapse into one misleading number. **This must propagate to EVERY
   consumer** (in-repo `masterminds.py`/`ai_desk.py` + the external Mastermind bot's gating + the
   news/narrative/qualitative feeds). Backward-compatible/additive contract so nothing breaks.
3. **Validation-gated wording.** Until the time-machine proves forward edge, show "high-confluence
   (context)" not "high-conviction (validated)"; emit a `validation_status` flag downstream.
4. **Scope = US stocks + baskets** (`us_stocks.html` + `baskets.html`); the shared cycle fix also
   improves China/HK/CA automatically.

## Root-cause flaws (audited, with evidence)
- **HWM buy-high (CRITICAL).** `cycles.py:726` Branch 1 tags a *late*-cycle name `FRESH BUY` on a
  shallow swing-low + 10d reclaim with only `macd_pos`. The `macd_approaching_dn`/`macd_curl_dn`
  flags (`cycles.py:116-124`) and higher-TF (3D/W) topping are computed but **never checked** in the
  buy logic. Measured live: **93 / 149 (62%) of `BUY NOW` signals fire late/stretched** (ECG day 93
  +46% over 200dma; MYRG day 68 +66%; FIX +57%). The cycle band `[36,42]` is **hard-coded for every
  stock** (`_preset`), so strong uptrends with shallow pullbacks read "approaching_band" wrongly.
- **Conviction ⊕ timing conflation.** `setups.py:85` ranks US by α only; the *urgency* tilt (±0.9) is
  the only timing that reaches rank; full ladder STATE + `bottom_confidence` discarded. The 0-100
  conviction dominates downstream → Mastermind buys OFG/EWBC into a topping daily cycle.
- **Verdict text lies.** `stock_score.py:798` stamps "High-conviction — leader with a good entry" by
  score bucket; OFG (α 0.07, entry WAIT) gets it. Verb must reflect *actual* leadership + *actual* entry.
- **No valuation-multiple awareness.** `stock_score.py:625-658` quality is durability-only; no
  forward-PE/PEG/EV anywhere. Engine punishes PRICE extension (200dma distance) not MULTIPLE
  extension — so a cheap-forward leader gets hard-capped for being above its MA (false NVDA veto),
  with no credit for cheap multiple/backlog. Fix = **non-veto haircut** (subtract-only, never blocks).
- **Uncalibrated, unbacktested.** Deep-PIT 2011-2026 collapsed SUE IC→~0; only insider survived FDR.
  `gate_go` always neutral; no per-ticker time-machine (`cycles.analyze()` latest-only; ladder_history
  is BTC-only). `validation.py` has the full honest toolkit (rank_ic, deflated_sharpe, purged_folds,
  newey_west, block_bootstrap) — unwired to the stock board.
- **Entry timing absent from the product;** dashboard card shows no window/target/cycle-day; verdict
  only cycle-capped on the detail page → dashboard-says-Buy / detail-says-Hold split on fast tops.

## Data assets actually present in THIS worktree (others are remote-only; design for null=absent)
PRESENT per-ticker: `site/stockdata/{T}.json` (1616; carries `valuation.forward_pe`/`value_z`,
`factors`, `analyst`, `earnings`, `accounting_quality`, `cycle`, `mtf`, `ladder`, `anticipation`,
`baskets_membership`, `smart_money`), `site/factordata/{alpha,factors,smartmoney}.json`,
`site/basketdata/{baskets,flow}.json`, `site/stockbrief/{T}.json` (catalyst LLM digests, firewalled),
`site/anticipationdata/{T}.json`, `site/gex/{T}.json` (36). Engines: `catalyst_stock`, `catalyst_tone`,
`smart_money`, `basket_score`, `narrative_rotation/regime`, `macro_news`, `news_vector`.
ABSENT here (remote-main only): `engine/intel_hub.py`, `engine/radar.py`, `financial_news`,
`altdata/by_ticker.json`, `engine/valuation.py`, `spotlight`. → Build the fusion from what's present;
expose an `intel_hub` interface so remote feeds slot in later.

## Downstream contract (PRESERVE keys; null = absent; ticker join de-duped by norm_company)
Consumers: `engine/stock_desk.py`, `scripts/build_{stock,china,canada,hk}_library.py`,
`scripts/build_site.py`, `scripts/build_stock_briefs.py`, `templates/dashboard.html.j2`,
`engine/masterminds.py`, `engine/ai_desk.py`; external **Mastermind** bot reads
`site/factordata/us_standouts.json` + per-ticker `stockdata`. Additive extensions only:
`conviction` keeps all current keys; ADD `conviction.validation_status`,
`conviction.conviction_validated{alpha_z,ic}` / `conviction.conviction_ensemble{composite_z,axes}`,
`entry_timing{status, opens_days, closes_days, pullback_target_pct, pullback_target_price,
next_trigger, entry_z_by_horizon{d3,d21,d63}, confidence, reason}`, `catalyst_list[]`,
`valuation_band`/`valuation_watch`.

## Architecture (new/changed modules)
1. `engine/cycles.py` (EDIT) — multi-TF rollover veto + per-stock band calibration so an
   extended/rolling-over name can never be `urgency='now'`. The HWM killer. Shared → fixes all boards.
2. `engine/entry_timing.py` (NEW) — gauge #2. status + pullback target $ + opens/closes days +
   horizon entry_z + confidence, from cycle/mtf/extension/ATR + catalysts.
3. `engine/valuation.py` (NEW) — sector-neutral forward-PE/PEG/EV-growth z → subtract-only quality
   haircut + `valuation_band` + `valuation_watch`. Never a veto, never a bonus.
4. `engine/stock_intel.py` (NEW, the `intel_hub` interface) — per-ticker fusion of alpha/insider/
   revisions/smart_money/gex/anticipation/baskets-flow/catalyst with signal-agreement + divergence
   flags. Feeds conviction as CONTEXT (tailwind + caveats), not blind scoring.
5. `engine/stock_score.py` (EDIT→conviction) — add valuation haircut; split validated/ensemble +
   `validation_status`; fix verdict mislabel (verb keyed on real leadership+entry); regime-staleness guard.
6. `engine/catalyst_fuse.py` (NEW or fold into stock_intel) — per-ticker `catalyst_list`
   [{date,type,days_until,impact_on_entry}] (earnings date already in stockdata; + macro calendar).
7. `engine/time_machine.py` + `scripts/backtest_stock_signals.py` (NEW) — PIT replay across history →
   per-ticker ladder_history → validation: **MAE/forward-return by entry verdict** (does the veto cut
   immediate drawdown?), rank_ic + deflated_sharpe + purged_folds on conviction, calibration curve →
   flips `validation_status`/trust tier.
8. UI: `templates/dashboard.html.j2` (stocks) + `stock.html.j2` + `baskets.html` — two-gauge cards,
   entry-window card, cycle-position chip, catalyst chips, validation badge, **card-time veto** on
   both pages.
9. Consumers: `masterminds.py` + `ai_desk.py` adopt two-gauge; **Mastermind bot** gating spec
   (selection←conviction_validated, WHEN←entry_timing.status, size←validation_status).

## Phases (each ships + tests; build never breaks)
- **P1** cycle-top fix in `cycles.py` + unit tests + backtest proof (MAE on buy-now ↓).  ← START
- **P2** `entry_timing.py` engine + emit + tests.
- **P3** `valuation.py` + `stock_intel.py` fusion + conviction split/verdict fix + tests.
- **P4** time-machine backtester + validation gate + calibration report.
- **P5** UI two-gauge on us_stocks (dashboard.html.j2) + stock.html.j2.
- **P6** baskets.html member entry signals + basket entry timing.
- **P7** in-repo consumers + Mastermind integration spec/edits.
- **P8** full suite + build verify + backtest writeup.

## PROGRESS (shipped on this branch)
- **P1 cycle-top fix** (`engine/cycles.py`): `ladder_state` now computes `rollover_veto`
  (htf 3D/W down-cross · confirmed daily down-cross+firm RSI · any daily curl/cross-down while
  late) and feeds the existing `extended_gate` so a late/rolling-over name routes to TOP WATCH /
  DON'T CHASE; `entry_timing` downgrades stretched reclaims to BUY SOON (imminent), never 'now';
  added `cand_depth_pct` to distinguish a real pullback from a continuation wobble. Measured:
  stretched 'now' 62%→0%, 32 bad signals removed, 0 regressions, 41 fresh buys preserved. Backtest
  (`scripts/_cycle_fix_backtest.py`): 'now' beats 'caution' on fwd-ret (+0.69 vs +0.41%), MAE
  (−2.87 vs −3.11%), win (56 vs 53%). Tests in `tests/test_cycles.py`.
- **P2 entry gauge** (`engine/entry_signal.py`): `assess(close, high, rec)` → {status, headline,
  buy_zone{low,high,pct_from_spot}, chase_above, stop, spot, atr_pct, horizon{d3,d21,d63},
  confidence, act_level, timing{opens_in_days_lo/hi}, cycle_pos{dc_day,dc_band,pct_through,phase}}.
  Zone depth capped at max(10%,3·ATR). Wired into `build_stock_library` → `stockdata` +
  `us_standouts.json` rows. Tests `tests/test_entry_signal.py`.
- **P3 valuation + verdict + validation** (`engine/valuation.py` + `engine/stock_score.py`):
  forward-aware non-veto haircut (NVDA fwd 17× → 0 haircut; trailing-only light-touch);
  verdict drops the false "good entry" claim and is validation-gated ("high-confluence (context)"
  until `gate_go`); new fields `valuation_band/watch/note`, `validation_status`. Tests
  `tests/test_valuation.py` + updated `tests/test_stock_score.py`. 118 tests green; full
  `build_stock_library` clean (1216 names, 28s); of 120 conviction names only 17 read buy-now,
  ZERO stretched names read buy_now.
- **P5 UI**: `templates/dashboard.html.j2` (mode=stocks) standout cards now show TWO gauges —
  OWN-IT conviction score + valuation chip, and a separate ENTRY strip (status dot, headline, buy
  zone $, cycle-day bar, window). Board merged buy+watch, conviction-ranked, so HWM stays visible
  as "wait". `templates/stock.html.j2` detail hero gets the same entry gauge + valuation chip.

## Mastermind bot integration spec (P7 — external repo `/Users/chriswong/Documents/Cluade/Mastermind`)
GOOD NEWS: the bot ALREADY adopts most of this for free.
- `portfolio/lenses.py` already has a HARD veto on `cycle_blocked` (caps size 0) → HWM (now
  cycle_blocked=True) is auto-vetoed. And `portfolio/conviction.py` `candidates()` reads the
  `us_standouts.json` **buy** list, which the cycle fix already prunes of topping names.
- DON'T live-edit it from here: it's on `master` with a parallel session's uncommitted changes,
  and its `vendor/macro` symlink points at the MAIN macro checkout (not this worktree) — so a new
  lens would be inert until this branch merges + vendor/macro updates.
- WHEN merged, the bot SHOULD add (additive, contract is backward-compatible):
  1. an `entry_timing` lens reading `stockdata.{T}.entry_signal.status`: ENTER/size only when
     status ∈ {buy_now, partial}; status ∈ {extended, wait_pullback, topping, buy_soon} ⇒ admit to
     the conviction book (own-it) but defer entry / 0 starter size until it opens. This is the
     two-gauge split on the bot side.
  2. scale size by `conviction.validation_status` (neutral_ic ⇒ context/smaller; positive_ic ⇒ full).
  3. surface `entry_signal.buy_zone` as the limit/accumulate band in the review queue.
  The conviction SCORE stays the selection signal; entry_signal is the WHEN; cycle_blocked stays the
  hard veto. Preserve all existing keys (null=absent; Brain keys on slug).

## Honest-validation metric that reconciles the prior "timing dilutes alpha" Phase-0
Their Phase-0 measured *selection* (does timing change WHICH names → forward return). It never
measured **entry quality** = next-5/10-day **Max Adverse Excursion (MAE)** conditioned on the entry
verdict. Timing should NOT change selection; it should cut immediate drawdown. The backtest's headline
test: among same-conviction names, do `entry_open` verdicts have materially lower MAE / faster
time-to-green than `extended/wait` verdicts? That is the edge the cycle-top veto must demonstrate.
