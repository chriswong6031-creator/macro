# Short-Side Phase-0 — Breakdown Event Definitions (PRE-REGISTRATION)

**Author:** Fable (orchestrating session), 2026-07-06
**Status:** pre-registered BEFORE the event dump runs. Thresholds FROZEN; changing them after seeing results is p-hacking. Amendments require a dated entry below, committed before the amended run.
**Governing charter:** `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md` §4; build spec `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` §6 (RUL-P6 paired-contrast law).

## §0. What is already known (priors)

Exit-routing is a settled NO-GO; EMA8 is a display tail-flag that rescues drawdown on 81–92% of deepest-DD-quartile names but fails the joint capture gate; froth/fragility topping legs exist at index/cohort level only; short interest has no PIT history. Nothing per-name exists for breakdown species. Base rates are unknown — measuring them is this study's purpose.

## §1. Hypotheses (descriptive Phase-0 — no verdict gates)

Three event definitions. Phase-0 is DESCRIPTIVE: it produces event counts, base rates, and paired two-sided forward grades. No promotion, no verdict, no claim beyond the printed table. `TrialLedger.log_declared_budget(3, family='short_side')` is logged before the run (3 = the three definitions; there is no threshold search).

## §2. Universe and data (frozen)

- Universe: union of (a) all tickers appearing as fires in `data/replay/replay_boarded.parquet`, (b) the current US board universe as constructed by the entry stack. Bounded ~1–2k names.
- Price plane: `massive_stock_day`, `split_adjust()` applied (import from `scripts.replay_standout_pipeline`). Window: ERA LAW only — events datable 2021-07-06 → present, and only bars with ≥252 prior bars of history on the plane.
- Liquidity floor: 21d median dollar volume ≥ $5M at event date; price ≥ $3.
- Vintage stamp mandatory on the summary (program RUL-P4).

## §3. Event definitions (frozen)

All computations close-only unless stated; H/L/C from the massive store where needed for the range proxy. Let `C` = split-adjusted close.

**BD-1 — Distribution under a pinned tape (per-name S1⁻/S2⁻ family):**
- `pinned`: event-day close within 3.0% of the rolling 63-bar max close.
- `lower_high`: the most recent 21-bar swing high is BELOW the prior 21-bar swing high (swing high = local max over ±5 bars), both within the trailing 63 bars.
- `ad_deterioration`: 21-bar sum of `sign_volume` is ≥1.0σ below its trailing-252-bar mean, where per-bar `sign_volume = volume × ((C−L)−(H−C))/(H−L)` (bars with H==L contribute 0).
- Event fires on the first bar all three hold.

**BD-2 — Failed reclaim after a stopped fire (S6⁻):**
- Source rows: `replay_boarded` fires with `state_8_21 == 'STOPPED'`.
- Within 10 bars after the stop bar (first bar where close ≤ 0.95 × entry), a rally whose highest close remains BELOW the fire-day close.
- Event fires on the first down-close after that failed-rally high (the failure bar).

**BD-3 — Tail-flag breach with defensive bid (S4⁻-adjacent arming):**
- `ema8_breach`: fresh breach per the canonical `engine/signal_quality` construction (3B resample, span=8, fresh_breach mask) — imported, never re-implemented.
- `extended`: event-day close ≥ 1.15 × rolling 126-bar min close.
- `defensive_bid`: mean of {XLP, XLU, XLV} 21-bar total return minus SPY 21-bar return > 0 on the event day (yahoo adjusted plane for the ETFs; adjustment-mode stated in the stamp).
- Event fires on the breach bar when all three hold.

**Episode collapse (all definitions):** per ticker per definition, events within 21 bars of a prior event collapse into that episode (first event wins). Cross-definition overlaps are kept and reported (an event may be BD-1 and BD-3 simultaneously; the overlap matrix is part of the output).

## §4. Grading (frozen; paired two-sided per RUL-P6)

Entry = next-bar close after the event bar (fill_offset=1). Horizons 21/63/126 bars. Both graded on identical paths:
- Long-side: existing `terminal_state` semantics — stop 0.95, cushion 1.05, liftoff 1.08@21 / 1.15@126; plus fwd_ret/mdd/mfe at each horizon.
- Short-side mirror: `terminal_state_short` — adverse = close ≥ 1.05 × entry; favorable = close ≤ 0.92 × entry @21 / ≤ 0.85 × entry @126; plus the mirrored excursion stats.
- Paired contrast: per event, the pair (long-side grade, short-side grade); asymmetry statistics computed on paired differences only. Baseline context: same stats on a matched random-bar control (same ticker, uniformly sampled non-event bars passing the same liquidity floor, 3 controls per event, seeded RNG).
- Censored paths flagged, never silently dropped.

## §5. Survivorship bound

The universe keys off fire-tape tickers and the current board — names delisted before ever firing are absent; `survivorship_biased=True` is stamped, with the note that the ERA-LAW window (2021+, massive plane, includes delistings post-listing) bounds the bias for within-window events. `dead_name_coverage_pct` carried from `data/edgar/_dead_name_coverage.json`.

## §6. Pre-committed output (and what would count as interesting)

The deliverable is the table: per definition — episode count, per-year counts, base rates of each terminal state both sides, paired asymmetry deltas with episode-clustered bootstrap CIs, control-baseline comparison, overlap matrix. Pre-committed reading guide (NOT gates): a definition is *worth a Phase-1 prereg* if its long-side stop rate exceeds the matched control's by ≥5pp with a CI excluding 0 at the paired-cluster level; it is *avoid-only* if long-side degrades but short-side favorable rate does not exceed control; a definition with <100 episodes is parked as underpowered regardless of point estimates. These readings gate nothing — they only shape which Phase-1 preregs get written.

## §7. What this does NOT show

No claim about live tradability, short execution, borrow, or timing precision; no claim that any definition is a signal; no cross-definition ranking (three definitions, no FDR-corrected selection among them in Phase-0); nothing here feeds any board, gate, alert, or score.

## Amendments

(none)
