# Bottom-Confidence score (multi-timeframe) — measured record + build plan

**Question (user).** Backtests showed the `DECLINE` state has the *highest* forward
return **and** the *deepest* drawdown. How do we reconcile that, and what factors
let us **accurately time near bottoms** — ideally an explicit **confidence of an
absolute bottom**, especially on the **weekly / monthly** timeframes? "I think we
have a confidence score but don't know if it's tied explicitly to this."

**Short answer.** (1) The paradox is a *bimodal-average* artifact — `DECLINE` mixes
V-bounces with falling knives; the mean is the bounces, the drawdown is the knives.
(2) We already have the confidence score — `engine.cycles.entry_quality` — and it
**works**: it cleanly sorts the bottoming blob by forward drawdown and "did the low
hold." (3) Its gap is exactly the user's instinct: it is **daily-cycle anchored**;
weekly enters only as a binary regime *gate* and there is **no monthly** input.
The build is therefore an *extension* of proven machinery, not new infrastructure.
Builds on [ENTRY_QUALITY.md](ENTRY_QUALITY.md).

---

## Method

Walk-forward over the **109 deep-history names** (`data/stocks/*`, median ~40y, all
regimes), weekly step on a trailing 600-day window — the same no-look-ahead machinery
`calibrate_ladder` / `entry_quality` use. State at bar *i* is computed from
`close[i-600:i+1]` only; outcomes from `close[i+1 : i+1+fwd]`. Restricted to the
**bottoming population** (states `DECLINE / BOTTOM WATCH / TURN SIGNALED / FRESH BUY
/ COUNTERTREND BOUNCE`). **68,916 evaluations.** Honest lens (D43): forward
**drawdown p10** (the tail dip you sit through) + **"held21"** = did the cycle low
survive the next 21 days (the cleanest "was this an absolute bottom" proxy), *not*
endpoint return. Monthly timeframe added via a causal month-end resample
precomputed per name. Harness: `scripts/research_bottom_confidence.py`.

> **Survivorship caveat (load-bearing).** This panel is 109 large-cap survivors in a
> ~40-year bull, so **every** bucket has a positive forward return — judge on
> drawdown + held-rate + *relative ordering*, never absolute return. Same caveat as
> ENTRY_QUALITY.md. The robust claim is **sign-consistency / monotonicity**, not the
> precise magnitudes (overlapping windows + correlated names ⇒ effective-N ≪ 68,916).

---

## Result 1 — reconciling the DECLINE paradox

`DECLINE`'s high mean return is a **mean over a bimodal distribution**: sharp
V-bounces (big winners) *and* falling knives (the −14% drawdown tail). You can't
harvest the mean without surviving the knives, so the raw state is a high-variance
lottery, not a signal. **The whole job of a bottom score is to sort that blob** —
which the next result shows we already do.

## Result 2 — `entry_quality` IS a real bottom-confidence score (monotone)

Bottoming population, bucketed by the existing **`entry_quality` long score** (0–100):

| eq_long band | n | fwd drawdown p10 (21d) | **held21** (low survived) | ret 63d |
|---|---:|---:|---:|---:|
| 0–20  | 20,430 | −14.2% | **29.6%** | +5.69% |
| 20–40 | 21,489 | −11.9% | **56.5%** | +4.80% |
| 40–60 | 15,004 | −10.8% | **68.9%** | +4.25% |
| 60+   | 11,993 | **−9.6%** | **74.5%** | +3.57% |

**Monotone and large-n.** Rising confidence ≈ **halves the drawdown tail** (−14.2→−9.6)
and **2.5×'s the "low held" rate** (30%→75%). Forward return *falls* (5.7→3.6) — the
fundamental trade confirmed: higher-confidence bottoms give up some of the explosive
bounce in exchange for far better risk/durability. **This is the answer to the
paradox** — sort `DECLINE` by `entry_quality` and the knives (low score, −14% tail,
30% hold) separate cleanly from the durable bottoms (high score, −10% tail, 75% hold).

## Result 3 — the multi-timeframe lever (the user's weekly/monthly ask)

Same population, split by whether each higher timeframe is **turning up**:

| split | n | held21 | drawdown p10 |
|---|---:|---:|---:|
| **weekly turning up** | 19,109 | **68.4%** | −12.1% |
| weekly NOT | 49,807 | 49.0% | −11.8% |
| **monthly turning up** | 21,764 | 57.4% | −11.6% |
| monthly NOT | 47,152 | 53.0% | −12.0% |

Confluence count {Daily, 3-Day, Weekly, Monthly all turning up}:

| confluence | n | held21 |
|---|---:|---:|
| 0 | 14,613 | 43.7% |
| 1 | 27,228 | 54.3% |
| 2 | 20,867 | 59.8% |
| 3 | 5,817 | **61.4%** |

**Findings:**
- **Weekly confluence is the strong, free lever: +19pp held-rate (68% vs 49%).**
- **Monthly is real but weak on its own (+4pp).** In 40y survivor names monthly turns
  are slow/rare; its value is in *combination* (the rare daily+weekly+monthly stack).
- **Confluence lifts DURABILITY (held-rate 44→61%) but not DRAWDOWN DEPTH** (flat ~−12).
  ⇒ Two orthogonal axes: **proximity/`entry_quality` governs how deep the dip risk is;
  multi-TF confluence governs whether the turn STICKS.** A good score needs both.

## Result 4 — what does NOT help (don't add it)

From the sibling audits (`scripts/_bt_signals`, `_bt_early`, 109 names): the
**anticipatory "early-topping" layer is noise** (forward +4%/63d, same as baseline —
it does not identify tops), and the `stoch>88` arm is *worse* than the RSI arm — the
same StochRSI-saturation failure just fixed in the ladder (commit 7044c73). Early
*bottoming* anticipation has marginal value (64% 63d hit) but only as a heads-up.
**Lesson (consistent with prior signal-accuracy research): more oscillators and pure
anticipation don't help; confirmation depth + orthogonal/higher-TF context do.**

---

## Proposed build — surfaced "Bottom Confidence" 0–100, multi-timeframe

Extend (not replace) `entry_quality` into a displayed **Bottom Confidence** for
buy-setups, combining the two measured axes + confirmation + regime:

```
BottomConfidence = 100 · gate · proximity_term · ( w1·confirmation + w2·multiTF_confluence )
```
- **proximity** (drawdown-depth axis) — existing `_eq_proximity` to the cycle low. *Dominant.*
- **confirmation** (existing `up_hold`) — swing-low → reclaim 10dMA → MA turning up.
- **multiTF_confluence** (NEW, durability axis) — Daily/3-Day/**Weekly** (heaviest, measured
  strongest) /**Monthly** (small bonus) turning up. Weight by the measured held-rate lift.
- **gate** — existing regime (bull/neutral/bear) × failed-cycle × liquidity tailwind.

**Surface it transparently** (the system's house style — show *why*, per-timeframe):

> **Bottom Confidence 78 / 100** — Daily ✓ · Weekly ✓ · Monthly ✗ · low holding ✓ · liquidity tailwind ✓
> *Higher = a more durable, lower-drawdown bottom. Not a return forecast — it trades upside for risk/durability.*

### Phasing
- **Phase 1 (cheap, high-value).** Add Monthly to `mtf_snapshot` (one resample) and a
  `multiTF_confluence` term to `entry_quality`; relabel/surface the buy-side magnitude as
  "Bottom Confidence" with the per-timeframe breakdown. Calibrate walk-forward (bucket →
  drawdown + held-rate), ship `bottom_confidence_calibration.json` like the ladder.
- **Phase 2 (orthogonal, needs data).** Capitulation/washout factors — the *absolute*-bottom
  tells the system lacks: volume climax (volume backfill in progress), market **breadth
  thrust** (breadth caches already collected), VIX/MOVE spike-then-rollover, distance below
  the 200-day. These are independent of cycle timing and should *add* separation.
- **Non-goal.** Predicting the exact low (the cycle band catches ~70% by design) or treating
  the score as alpha. It is a **risk/durability** score — calibrated and labeled as such.

### Honest ceiling
You cannot reliably call the exact bottom; the win is **confidence-weighting** — trading some
upside for a much higher chance the low holds. The data says we can express that well today
on the **daily+weekly** axes (the strong levers) and add monthly + capitulation for the rare
high-conviction "generational" bottoms.
