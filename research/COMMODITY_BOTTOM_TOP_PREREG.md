# COMMODITY_BOTTOM_TOP — PRE-REGISTRATION

**Organ:** Durable-bottom / Euphoric-top Confluence Organ.
**Engine file:** `engine/commodity_confluence.py`.
**Status:** DISPLAY-TIER — ships with no scored authority. Nulls are printed.
This document pre-registers the FUTURE promotion of this organ to authority-tier.
**Author:** build agent, 2026-07-12. **Constitution:** house law §Epistemics.

LLMs do not originate, score, or escalate these signals. The scores are
deterministic boolean aggregates of existing engine outputs (MTF ladder, arming
detector, COT positioning, residual shock). Nothing here carries forward
calibrated edge until the gauntlet below is cleared.

---

## 1. Construction (frozen — deterministic)

> **Amended 2026-08-05 (A1, pre-run).** The top-side `divergence` condition now
> additionally requires the cycle position to be OUTSIDE the bottoming zone.
> See §6. No gauntlet has been run against this organ, so no result informed the
> change.

Two mirrored 0-100 sides: **washout bottom** and **euphoric top**.

Score formula (availability-normalised K-of-N):

    score = 100 × Σ(weight_i for fired conditions_i) / Σ(weight_i for applicable conditions_i)

If Σ(applicable weights) = 0 OR n_applicable < `min_applicable` (default 3) → score is None.

### Bottom conditions
| Code          | Weight key   | Fires when | Applicable when |
|---|---|---|---|
| shock_bottom  | shock (2.0)  | macro shock_z ≤ −1.5 OR price shock_z ≤ −1.75 | shock value present |
| oversold_ltf  | oversold_ltf (1.0) | D stoch ≤ 20 AND (3D stoch ≤ 25 OR D rsi14 ≤ 35) | D mtf present |
| oversold_htf  | oversold_htf (1.0) | W stoch ≤ 25 OR W rsi14 ≤ 40 | W mtf present |
| curl          | curl (1.5)   | D/3D macd_curl_up OR D stoch_cross_up | D mtf present |
| armed         | armed (1.5)  | technical_arming `armed` == True | arming ran (stoch_k non-null) |
| bc_conf       | bc_conf (2.0)| ladder bc_score ≥ 40 | bc_score present in ladder |
| cot_short     | cot (1.0)    | pos_pctile ≤ 15 | pos_pctile present |
| cycle_bottom  | cycle (1.0)  | phase ∈ {Trough, Recovery, Accumulation} | cycle_positions.json has member |
| breadth_bottom| breadth (1.5)| breadth_pctile ≤ 0.10 | index level only, breadth dict passed |

### Top conditions
| Code          | Weight key   | Fires when | Applicable when |
|---|---|---|---|
| shock_top     | shock (2.0)  | macro shock_z ≥ +1.5 OR price shock_z ≥ +1.75 | shock value present |
| overbought_ltf| oversold_ltf | D stoch ≥ 80 AND (3D stoch ≥ 75 OR D rsi14 ≥ 65) | D mtf present |
| overbought_htf| oversold_htf | W stoch ≥ 75 OR W rsi14 ≥ 60 | W mtf present |
| curl_dn       | curl (1.5)   | D/3D macd_curl_dn OR D stoch_cross_dn | D mtf present |
| stretch       | stretch (1.5)| close/SMA200 − 1 ≥ 0.25 | ≥ 200 bars |
| divergence    | divergence (2.0)| ts_trend == "up" AND momentum_state == "bear" AND price still elevated (D stoch ≥ 50 OR close ≥ SMA200) AND cycle pos > 32 *(A1)* | both columns present AND (D stoch OR SMA200) present AND not suppressed by A1 |
| cot_long      | cot (1.0)    | pos_pctile ≥ 85 | pos_pctile present |
| cycle_top     | cycle (1.0)  | phase ∈ {Peak, Downturn, Distribution} | cycle_positions.json has member |
| breadth_top   | breadth (1.5)| breadth_pctile ≥ 0.90 | index level only |

### State mapping
- bottom ≥ 60 AND bottom > top → "Washout bottom forming"
- top ≥ 60 AND top > bottom → "Euphoric top risk"
- bottom ≥ 40 AND bottom ≥ top → "Basing — early bottom signs"
- top ≥ 40 AND top > bottom → "Extended — late cycle"
- max(n_applicable) < min_applicable → state = None, null_reason = "insufficient signal"
- else → "Neutral"

---

## 2. Display-tier commitment

Until the gauntlet below is cleared, this organ:
- Is presented as **display-only context** — no scored authority, no allocation gate.
- Prints **honest nulls**: a null score and the null_reason are emitted and shown,
  never hidden.
- Is labelled deterministic, not predictive, in all UI surfaces.
- Does not feed any allocation, ranking, or gating signal.
- The word "validated" is CI-guarded and must not appear in any display text.

---

## 3. Pre-registered promotion gauntlet

**Organ family:** COMMODITY_BOTTOM_TOP.
**n_trials budget:** 20 (all condition-weight variants + threshold configs explored
during any future tuning pass; conservative over-estimate per de Prado DSR recipe).

### 3.1 Horizon ruler (pre-committed)
- **Primary horizon role:** `bottom_forming` → 63-calendar-day forward excess return
  vs equal-weight commodity index benchmark (the horizon that distinguishes a durable
  bottom from a countertrend bounce; not a short-term or open-ended exit).
- **Robustness rows (non-gated, same family):** 21d and 126d — reported as a curve,
  verdict at 63d only.

### 3.2 Statistical gates (ALL must clear for promotion)

1. **DSR ≥ 0.90** at n_trials = 20 (Deflated Sharpe Ratio; de Prado haircut on the
   Sharpe of the 63d forward excess return stream at entry dates). This is the only
   door to authority.
2. **HAC t-stat ≥ 2.0** (Newey-West, lags = 4) on the non-overlapping episode excess
   returns for the "Washout bottom forming" state.
3. **BH-FDR q ≤ 0.10** within the COMMODITY_BOTTOM_TOP family (covers both the bottom
   and the top sides as two trials in the family).
4. **Split-half sign-stability:** split at 2013-01-01; mean excess return must be same
   sign in both halves for a GO.
5. **Leave-one-crisis-out:** re-run removing each of {2008, 2015, 2020, 2022} episode
   clusters; mean excess must remain positive in each held-out version.
6. **Effective-N floor:** ≥ 8 independent (non-overlapping) episodes required across
   the full 17-member × ~25-year panel before promotion is eligible.

### 3.3 Top-side (euphoric top)
Same gauntlet applied to the "Euphoric top risk" signal, with the forward metric
being negative excess return. Top side is a SEPARATE trial in the same BH-FDR family.

### 3.4 Verdict rules
- **GO** — all 6 gates above clear for that side (bottom or top).
- **ACCRUE** — HAC t in [1.0, 2.0) OR DSR in [0.50, 0.90) with positive sign; real
  but underpowered. Retain display-tier, schedule re-run when N grows.
- **NO-GO** — mean excess ≤ 0, or split-half sign-flips.
- **KILL** — HAC t ≤ −2.0 for the pre-registered direction; closes this specific
  construction. "Not found yet" ≠ "does not exist" — search for a better ranker.

---

## 4. What this test does NOT show (pre-committed)

- Not a tradeable strategy net of costs, slippage, or capacity.
- Not causal: confluence of technical states correlates with macro states that also
  drive forward commodity returns.
- Not survivorship-free at the name level; the 17 complex members are the current
  roster (some with histories starting well after 2000).
- The organ is asset-agnostic (no per-commodity polarity correction); a future
  per-asset tuning would count as a new trial family, not an update to this one.

---

## 5. Registry

Experiment id: `commodity_bottom_top_v1`.
Maturation: first nightly build after P3 bridge (`cycle_positions.json`) is live.
Come-back-on: when cycle_positions.json first populates (P3) AND when n_episodes
across 17 members reaches the effective-N floor of 8.

---

## 6. Amendments

Construction changes made after this document was first written. Each records
whether any gauntlet result existed at the time — an amendment made after seeing
a result is a different (and far weaker) epistemic object than one made before.

### A1 — 2026-08-05 — divergence gated out of the bottoming zone

**Status when amended: NO GAUNTLET HAS EVER BEEN RUN on this organ.** §3 is still
entirely unexecuted — there is no DSR, no HAC t, no split-half, no episode count,
and therefore no result that could have informed this change. This is a **pre-run
construction amendment**, disclosed here before any measurement exists.

**Change.** The top-side `divergence` condition additionally requires the member's
cycle position (`data/commodity/cycle_positions.json` → `pos`, 0-100) to be **> 32**.
At `pos ≤ 32` the condition is dropped from the top side entirely — it is marked
NOT APPLICABLE, so it feeds neither the numerator nor the denominator of the top
score — and is surfaced instead as a display-only boolean, `turn_developing`.
Threshold 32 is not new: it is the bottoming-zone boundary `engine/sector_cycles.py`
already uses (`pos <= 32` → Trough/Recovery). Config key:
`commodities.confluence.divergence_bottoming_pos_max` (default 32.0).

**Why.** The construction reads "long trend up, momentum hysteresis flipped bear,
price still elevated" as a ROLLOVER. At the bottom of the long cycle that is the
RECOVERY signature, not a top: the slow trend anchors (ema_trend / ema_cross /
sma200) still carry the prior downtrend, so `momentum_state` lags bear while price
turns up off the low. On 2026-08-03 gold (`pos` 1.7, Recovery) and silver (`pos` 1.0,
Trough) each fired it as the ONLY top-side condition — a top-risk contribution at
the exact position the cycle clock called cheap. Both members' `rollover_score` read
44.4 on that single condition.

**Direction of the change.** Strictly a reduction in top-side score: removing a
FIRED condition from an availability-normalised ratio can only lower it (18.2 → 0.0
for gold and silver; 31.8 → 16.7 for platinum, which had other top conditions
firing). No condition was added, no weight was changed, and the bottom side is
untouched. Nothing here promotes anything to authority — the organ remains
display-tier under §2.

**Trial accounting.** Counted against the §3 `n_trials` budget of 20 as one trial,
leaving 19 — the conservative treatment. It is recorded as a trial even though no
result was observed, so that a future gauntlet cannot be accused of an unbudgeted
degree of freedom.

**Pinned by:** `tests/test_commodity_confluence.py` —
`test_divergence_active_above_bottoming_threshold`,
`test_divergence_suppressed_inside_bottoming_zone`,
`test_divergence_suppression_is_position_driven_only`,
`test_divergence_threshold_boundary_is_inclusive_at_32`,
`test_divergence_gate_open_when_cycle_position_absent`,
`test_turn_developing_requires_the_divergence_shape`.

**Not amended:** `technical_arming.armed` (the `armed` bottom condition in §1) is
byte-identical. The sibling W-C change added a separate display-only
`armed_recent` state; it is NOT a condition in this organ and feeds no score.
