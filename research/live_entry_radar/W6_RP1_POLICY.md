# W6 RP1 — deterministic Research Priority policy (frozen before ranking code)

**Status:** ACCRUING / RESEARCH PRIORITY. Not a prediction. Not W7.
**Policy version:** `RP1`
**Schema:** `mastermind.research_priority.v1`
**Frozen:** 2026-08-17, before any additional outcome-conditioned table was inspected
for the purpose of improving this formula. W5 confirmatory results
(`research/live_entry_radar/W5_CONFIRMATORY_RESULTS_2026-08-17.md`) were already
known and are therefore **contaminated for weight choice**. They are not inputs.

## What the number is

`priority_index` is a **deterministic Research Priority index under policy RP1**:
the equal-Borda mean of available dimension percentiles within the current
rankable population, scaled 0–100. `ordinal` (1 = look here first) is the
**product function**. Rank is competition-ranked (ties share an ordinal).

It is **not** probability, confidence, conviction, expected return, expected
upside, win rate, percentile of future performance, or edge.

A value such as 91 must decompose into named dimension percentiles and the
raw point-in-time measures those percentiles were ranked from.

## Unit of ranking

One **episode / expert observation** `(ticker, detector_id, variant)`.
NVDA G0, NVDA C2a, NVDA C5 remain three rows. Never a ticker-wide average.

## Rankable population

An observation is rankable iff all of the following hold:

1. The live cycle is not a whole-cycle refusal (`killed`, `out_of_window`,
   `stale_pack`, `proof_failed`, `failed`).
2. The name row is `evaluated` (not dark / basis-mismatch / pack-integrity /
   no-quote / stale-quote / no-substrate).
3. The latest observation is not `stale` or `unavailable`;
   `history_freshness` is `confirmed`.
4. The episode is nonterminal and past PROBING (`ARMED` / `TURNING` / `CANDIDATE`).
5. At least **two** of the four RP1 dimensions have a finite measure.

Stale ≠ low priority: a stale live read is **unrankable**, reason
`stale_observation`. Missing ≠ zero: an unavailable measure is omitted, never
filled with 0. Coverage below two dimensions → unrankable,
`insufficient_coverage`.

Whole-pass `health.state == degraded` caused by *other* names does **not**
unrank a healthy episode. Cycle-refusal states do.

## Dimensions (equal Borda — not edge weights)

No 30/20/20 hand weights. Each available dimension contributes one percentile
in the rankable set. The composite is the mean of available dimension
percentiles. That is an attention-ordering rule, not an estimate of edge.

### A. `structural_quality` (higher better)

From confirmed daily closes **strictly before** the evaluation session
(`DailyHistory.confirmed_through`):

| measure | definition | direction |
|---|---|---|
| `ret_20` | close/close[−20] − 1 | higher |
| `ret_60` | close/close[−60] − 1 | higher |
| `ret_120` | close/close[−120] − 1 | higher |
| `proximity_120` | close / max(close, 120) | higher |

A submeasure with insufficient history is unavailable.

### B. `reset_quality` (orderly reset, not deeper damage)

Depth is **not** authority (`DNR:KILL-WASHOUT-TURN` adjacent; C4/depth firewall).

| measure | definition | direction |
|---|---|---|
| `structure_intact` | 1 if close ≥ SMA50 else 0 | higher |
| `pulled_back` | 1 if close < 0.98 × max(close, 20) else 0 | higher |

No ATR-drawdown magnitude. No “more oversold → better.”

### C. `resilience_quality`

| measure | definition | direction |
|---|---|---|
| `rs_60_vs_bench` | `ret_60` − SPY `ret_60`, only if SPY is in the pack substrate | higher |
| `oscillator_reset_intact` | 1 if (K < 20) AND `structure_intact` else 0 | higher |

If SPY is absent, `rs_60_vs_bench` is unavailable — never a probe-set median
(that would launder hot-universe composition into RS).

### D. `recovery_quality` (knowable at the observation timestamp)

| measure | definition | direction |
|---|---|---|
| `rebound_atr` | (sampled_close − running_sampled_low) / ATR(14) prior confirmed | higher |
| `hist` | current RSI-MACD histogram on the observation | higher |
| `k_minus_d` | K − D on the observation | higher |

Post-arm volume/RVOL is **not** granted a weight (contract §9: candidate
research, not earned authority).

## Explicit exclusions (hard firewalls)

These never enter a measure, a dimension, or a tie-break:

- admission-time hotness / Layer-C attention
- lobe nomination count or badge identity
- ticker identity (no fixed effect; ticker is address only)
- per-name historical outcomes (win rate, return, MFE, MAE, false-start, accuracy)
- W5 question outcomes, including G0’s Q5 +13.4-session earliness
- C4 `recovery_count`, MTF washout depth, C4 turn×washout fusion
- page mentions, sentiment, “more organs noticed it”
- LLM output
- detector identity as a bonus (G0/C5 get no expert-family points)
- `live_pack` inversion thresholds as a quality score

## Aggregation / order law

1. Extract whitelist-only measures. Unknown keys on the input object are ignored
   (outcome-injection firewall).
2. For each dimension, percentile-rank the mean of its available submeasures
   across the rankable set (higher better). Dimension with zero submeasures →
   unavailable.
3. `priority_index` = round(mean of available dimension percentiles).
4. `ordinal` = competition rank of `priority_index` (1 = highest index).
5. Board display order: `ordinal`, then `detector_id`, then `variant`, then
   `ticker`. Ticker is a stable sort key, **not** a feature: identical measures
   share an ordinal regardless of ticker.

## Tie-breaking

Competition rank. No ticker-name, no detector-id bonus. Identical measures ⇒
identical `priority_index` and `ordinal`.

## Null / stale / degraded

| condition | result |
|---|---|
| missing required history for a submeasure | that submeasure omitted |
| fewer than two dimensions | `unrankable`, `insufficient_coverage` |
| stale observation or stale history | `unrankable`, `stale_observation` |
| dark name / refused tape / basis mismatch | `unrankable`, named reason |
| whole-cycle refusal | empty board, `cycle_refused` |
| partial coverage (≥2 dimensions) | ranked; `unavailable` lists the rest |

## Freshness / PIT

Every measure uses only:

- confirmed daily bars strictly before the evaluation session, and
- the latest observation at `observed_at`.

`known_at` = that observation’s `observed_at` (live) or the pack `as_of`
(confirmed-bar nightly lanes). No future close, no completed later bar, no
W5 outcome, no reconstructed “today as history.”

## Correction behavior

Live Priority is **ephemeral on the live payload**. The durable episode ledger
keeps `research_priority: null` (W4 `NULL_ONLY_FIELDS`). A corrected upstream
frame recomputes current Priority; it does not rewrite ledger history.

Provenance binds `policy_version`, episode identity, `pack_hash` /
substrate fingerprint, and `known_at`.

## Lifecycle independence

Computing or changing Priority never writes `state`, `first_armed_at`,
`candidate_at`, invalidation, expiry, or event lineage.

## User-facing meaning

Glance copy: **Research Priority (ACCRUING)**. Mechanical why-now only.
No “validated”, no probabilities, no “AI says buy.”

## Where it is computed

At the existing live evaluation **projection** seam
(`engine/entry_radar/live_eval.py` → payload). Not in `live_pack.py`.
Not a second scheduler, ledger, daemon, or artifact family.

## V1 non-goals

W7 Opportunity Score. Fitted coefficients. Detector-rule changes. Prophet.
Production `entry_radar.html`. Auto-trading. LLM ranking.
