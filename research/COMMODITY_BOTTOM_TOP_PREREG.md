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
| divergence    | divergence (2.0)| ts_trend == "up" AND momentum_state == "bear" | both columns present |
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
