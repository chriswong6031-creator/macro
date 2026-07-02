# W0.4 — THE KEYSTONE GATE: does cycle POSITION / PHASE predict forward drawdown-adjusted returns?

**Verdict document. As of 2026-07-02.** The Cycle Intelligence Masterplan's biggest open
question, answered in one wave (`CYCLE_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §4 W0.4, §6
risk #1). Producer: `scripts/keystone_position_gate_phase0.py`. Cohort:
`data/research/keystone_tr0/` (**basis `tr`, epoch `tr_v0`, RESEARCH-ONLY** — ruling A1: no
user-facing badge may ever cite these numbers).

---

## 0 · TL;DR — the one-paragraph answer

On a leak-free PIT backfill of **8,344 month-end stamps** across the two membership-free
families (11 US SPDR sector ETFs + 24 single-country iShares ETFs), 2005-01 → 2026-06
(258 months, spanning 2008 / 2020 / 2022 drawdowns), **cycle POSITION does not predict
forward returns** — every position-decile return-gap CI straddles zero at 21/63/126d. The
**only reproducible signal is a drawdown (risk) signal carried by PHASE, and it inverts the
naive intuition**: the *Peak* phase precedes **shallower** forward drawdowns (63d p10-DD gap
vs base CI **[+1.2%, +5.0%]**) and the *Trough* phase precedes **deeper** ones (CI
**[−10.0%, −1.9%]**). The audit's suspected **LADDER inversion — that low-position / DECLINE
states out-perform high-position / FRESH-BUY states on the drawdown lens — is NOT confirmed
on PIT data; it is INCONCLUSIVE on every era × horizon**, and the point estimate leans the
*opposite* way in the full sample. Even the one real signal (Peak → shallow DD) **decays
out-of-sample** (significant pre-2018, straddles zero post-2018). **Program implication: the
prediction thesis (Phases 3–5) shrinks — the honest v1 product is tripwires + regime context
+ measurement + a *risk-only, phase-keyed* drawdown lens, not a position-decile return
engine.** A null on the return channel is a valid, valuable verdict (§6.1).

---

## 1 · Methodology (the anti-hand-wave section)

**Universe (membership-free families only).** 11 US SPDR sector ETFs (`SECTORS`, 1998→) +
24 single-country iShares ETFs (`country_cycles.COUNTRIES`, 1996→). **Baskets and blocs
SKIPPED** — their equal-weight level series depend on *current* membership (`pit=False`,
`sector_cycles.py:409`) and cannot be reconstructed point-in-time (masterplan D2 §0).

**PIT backfill (the loop).** For each calendar-month-end (last trading day), for each
series, stamp the engine's own cycle read — `pos, phase, signal, timing_state, osc_slope,
proj_central, dc_phase, action, above200d` — using **only tape ≤ the stamp date**. Driven by
`engine.sector_cycles.build_sector` / `engine.country_cycles._build_one` on a PIT-sliced
close panel (`closes[closes.index <= asof]`). This is the compute-frugal path: it produces
**byte-identical `now` fields** to `sector_cycles.compute(asof=)` (verified), at ~19× lower
cost because it skips the basket/amalgam construction that dominates `compute()`.

**PIT property — verified, not assumed.** The task's核心 requirement: *a stamp computed at
asof must not change when later data is appended.* Three spot-checks + one append-test, all
**PASSED**:

| check | ticker | asof | result |
|---|---|---|---|
| spot | XLK | 2024-03-31 | match=True (Peak, pos 84.3) |
| spot | EWZ | 2017-10-31 | match=True (Downturn, pos 59.8) |
| spot | XLF | 2019-01-31 | match=True (Recovery, pos 25.9) |
| **append-test** | XLK | 2015-06-30 | **match=True** — stamp on a tape truncated to 2015 is byte-identical to the stamp on the full 2026 tape sliced to 2015 (the 2016–2026 tail cannot move the 2015 read) |

The stamp is a pure function of `close ≤ t`; appending future bars provably cannot move a
past stamp.

**Forward outcomes (china grader convention, copied exactly —
`engine.china_sector_cycles_grader._fwd`).** Each stamp's forward window anchors at the
**first close STRICTLY AFTER the stamp date** (bar i+1, `searchsorted(side="right")`). For
h ∈ {21, 63, 126} trading bars, on the instrument's OWN price tape:
`fwd_ret_h = close[i+1+h]/close[i+1] − 1` and `fwd_maxdd_h = min(0, min(close[i+2..i+1+h]) /
close[i+1] − 1)`. No partial windows — an unmatured window is dropped, never estimated.
Matured: 8,309 / 8,204 / 8,099 of 8,344 stamps at 21/63/126d.

**Statistics (house rules; every cell carries its CI or is not reported).** Hand-rolled
numpy/pandas only (no sklearn/statsmodels). CIs are **month-block bootstrap** (resample whole
stamp MONTHS with replacement, 800 draws, seed 7) — the cross-section within a month is
correlated, so we resample DATES, not rows (masterplan ruling A2). Every cell counts
**n_months, not n_rows.** The drawdown-adjusted lens is `mean_fwd_ret / |p10_dd|` (return per
unit tail risk, masterplan D2 §4.1). Position is deciled **within family** (a structurally
high-pos family can't dominate a bin). Walk-forward framing: `full` / `pre_2018` /
`post_2018` sub-panels. Explicit inversion test (below).

**Runtime.** Backfill 882 s + study bootstrap ~2 min ≈ **~15–17 min wall** (well under the
30-min target; the full site render is NOT run). Deterministic given the same tape and seed.

---

## 2 · Results

### 2.1 Position deciles — NO return signal, at any horizon

Every decile's forward-return gap-vs-base CI **straddles zero**. Representative (63d, within-
family deciles, n_months per cell in the 128–220 range):

| decile | mean fwd ret | ret gap-CI vs base | p10 DD | dd-adj score | hit-gap |
|---|---|---|---|---|---|
| D1 (pos 0-10%) | +1.00% | [−4.6%, +1.5%] | −28.8% | 0.035 | −0.061 |
| D3 (pos 20-30%) | +3.63% | [−0.6%, +2.9%] | −20.3% | 0.179 | +0.010 |
| D5 (pos 40-50%) | +2.53% | [−1.1%, +1.1%] | −17.8% | 0.142 | −0.007 |
| D7 (pos 60-70%) | +2.57% | [−0.9%, +1.1%] | −16.6% | 0.154 | +0.023 |
| D9 (pos 80-90%) | +3.16% | [−0.6%, +1.9%] | −15.7% | 0.201 | +0.054 |
| D10 (pos 90-100%) | +2.25% | [−2.0%, +1.3%] | −16.1% | 0.140 | +0.024 |

The dd-adj score **rises mildly with position** (low deciles carry deeper p10 drawdowns → worse
dd-adj), but **no gap CI excludes zero**, so this is not a claimable edge — it is the mechanical
fact that washed-out names are in bigger drawdowns *and stay volatile*. **KG-1: NO-EDGE on the
return channel; not-claimable on the dd-adj channel.**

### 2.2 Phases — a DRAWDOWN signal, and it inverts the intuition

The **p10-drawdown gap-vs-base CI** is the one place signal survives the bootstrap (63d;
consistent at 21d and 126d):

| phase | n_months | mean fwd ret (gap-CI) | p10 DD **gap-CI vs base** | reading |
|---|---|---|---|---|
| **Trough** | 197 | +1.26% [−2.9%, +0.6%] | **[−10.0%, −1.9%]** | forward DD **DEEPER** than base ✓ |
| Recovery | 126 | +6.24% [−0.5%, +8.8%] | [−8.7%, +1.5%] | straddle |
| Expansion | 212 | +2.00% [−1.7%, +0.7%] | [−0.5%, +2.8%] | straddle |
| **Peak** | 214 | +2.57% [−1.0%, +1.2%] | **[+1.2%, +5.0%]** | forward DD **SHALLOWER** than base ✓ |
| Downturn | 223 | +2.89% [−0.7%, +1.6%] | [−0.9%, +3.5%] | straddle |

**Two CIs exclude zero, and they point the *opposite* way to the naive cycle story:** the
*Peak* (pos-high, "topping") phase precedes **shallower** forward drawdowns, and the *Trough*
(pos-low, "bottoming") phase precedes **deeper** ones. Mechanism (stated plainly, not sold):
a stamp lands in Trough because the tape is already in a washout with high realized vol —
forward 63d drawdowns from there are naturally deeper; a Peak stamp sits on a low-vol uptrend
whose forward drawdowns are shallow **until** the actual top, which the phase wheel (zero
hysteresis, D1) does not lead. **No phase carries a forward-RETURN signal** (every return
gap-CI straddles zero). **KG-2: a risk-only, phase-keyed drawdown signal exists; the sign is
the inverse of the intuitive mapping.**

### 2.3 The LADDER inversion test — NOT confirmed (the headline the audit was waiting for)

The audit suspected an inversion: low-position / DECLINE states out-performing high-position /
FRESH-BUY on the drawdown-adjusted lens (the china `ladder_calibration.json` showed DECLINE
+2.37% vs FRESH-BUY +1.13% on 21d endpoint return). On leak-free PIT data:

| era | horizon | ret gap (low−high) | dd-adj gap (low−high) | **verdict** |
|---|---|---|---|---|
| full | 21d | −0.02% CI[−1.9%,+1.6%] | −0.031 CI[−0.16,+0.12] | **INCONCLUSIVE** |
| full | 63d | −1.05% CI[−4.1%,+2.2%] | −0.104 CI[−0.25,+0.08] | **INCONCLUSIVE** |
| full | 126d | −1.77% CI[−6.0%,+2.1%] | −0.112 CI[−0.28,+0.05] | **INCONCLUSIVE** |
| pre_2018 | 21/63/126d | negative | −0.067 / −0.143 / −0.118 | INCONCLUSIVE (×3) |
| post_2018 | 21/63/126d | ~0 / ~0 / −0.022 | +0.025 / −0.003 / −0.059 | INCONCLUSIVE (×3) |

**The inversion is NOT confirmed on a single era × horizon cell.** Worse for the hypothesis:
in the full sample the point estimate runs the *other* way — high-position states carry the
*higher* dd-adj score (e.g. 63d: high-pos 0.170 vs low-pos 0.066) — but the gap CI straddles
zero, so we do not claim the reverse either. **KG-3: INVERSION REFUTED-LEANING / INCONCLUSIVE
— the ladder-inversion thesis does not survive PIT + month-block bootstrap.**

The exact DECLINE-vs-FRESH-BUY contrast (the china claim) reproduces as a *point estimate*
only — DECLINE 63d dd-adj **0.190** vs FRESH-BUY **0.062** — but DECLINE's own p10-DD gap-CI
**[−14.9%, +0.3%] straddles zero.** The china calibration's endpoint-return ordering **does
not survive** the month-block bootstrap when re-run PIT on this universe.

### 2.4 Walk-forward stability — the one real signal DECAYS out-of-sample

The Peak → shallow-DD and Trough → deep-DD signals hold **pre-2018** (Trough 63d ddgap-CI
[−0.212, −0.029]; Peak [+0.018, +0.070]) but **straddle zero post-2018** (Trough [−0.033,
+0.015]; Peak [−0.052, +0.040]). Only the pooled-full estimate is significant, driven by the
pre-2018 half (which contains 2008–2011, the deepest DD regime in the sample). **This is a
walk-forward fragility flag, not a stable edge** — the signal is really "in a
high-vol-clustering regime, washed-out names keep drawing down," which was strongest around
the GFC. Any downstream use must treat it as regime-conditional, not evergreen.

---

## 3 · VERDICT per claim (GO / REFINE / NO-EDGE)

| claim | verdict | basis |
|---|---|---|
| **Position deciles carry forward drawdown-adjusted signal** | **NO-EDGE** | every decile return-gap CI straddles 0; dd-adj monotonicity is not-claimable (no CI excludes 0) at 21/63/126d |
| **Phases carry a forward-DRAWDOWN (risk) signal** | **REFINE (regime-dependent)** | Peak→shallower / Trough→deeper DD CIs exclude 0 pooled, **but decay post-2018**; risk-only, never a return lever (doctrine #9) |
| **Phases carry a forward-RETURN signal** | **NO-EDGE** | every phase return gap-CI straddles 0 |
| **The LADDER inversion (low-pos/DECLINE > high-pos/FRESH-BUY, dd-adj)** | **NO-EDGE / REFUTED-LEANING** | INCONCLUSIVE on all 9 era×horizon cells; point estimate leans the opposite way in-full |
| **BUY/SELL transition badge predicts its promised move** | **NO-EDGE (this wave)** | signal cells straddle 0 on both channels; see study_tables `signal` block |

**One-line answer to the keystone question:** *Position deciles carry no forward
drawdown-adjusted signal; the only reproducible signal is a regime-fragile, phase-keyed,
risk-only drawdown lens whose sign inverts the intuitive cycle mapping; the ladder inversion
is not confirmed.*

---

## 4 · What this implies for Phase-3/4/5 scope (masterplan §6 risk #1)

The masterplan pre-committed (§6.1): *"If W0.4 finds position/phase deciles carry no forward
drawdown-adjusted signal, phases 3–5 shrink drastically and the honest product is tripwires +
regime context + measurement."* This wave lands close to that branch. Concretely:

1. **The hazard stack (D5 / Phase 4) is NOT vindicated by a position edge** — position is not
   the covariate. This does **not** kill the hazard model (it predicts *time-to-turn*, a
   different target than *forward-return-by-position*), but it **removes the a-priori reason to
   expect it to size positions**. D5's own honesty gate already says "most cells will ship
   PRIOR"; this wave adds: even a passing hazard cell must clear the **decision-linkage gates
   DL-1/DL-2** (PREREGISTRATION §6) before it sizes anything. **Recommend: build the hazard
   panel + KM baseline (W4.1) as a research surface; gate any user-facing sizing on DL-1.**

2. **The binding-calibration wave (W4.6 / BC-1) should expect to FAIL the return channel and
   at most PASS a risk-only, regime-flagged drawdown channel.** The ladder must not ship a
   fitted return score; if it ships at all it is a FRAME context strip ("historically, Peak
   phases preceded shallower 3m drawdowns *in high-vol regimes*; not a forecast"), never a
   BUY/AVOID conviction number. The DECLINE>FRESH-BUY china ordering must be re-labeled from a
   calibration input to an **unvalidated, regime-conditional observation.**

3. **Phase-3 product surfaces should center measurement + tripwires + regime context**, not a
   position-decile prediction. The Peak/Trough drawdown asymmetry is worth surfacing **only**
   as a MEASURED, regime-flagged, risk-lens badge with its walk-forward decay disclosed — it is
   exactly the kind of small, honest, size-only signal doctrine #9 blesses.

4. **The keystone does NOT shrink the *measurement* and *ontology* pillars (S1/S3/S6) at all**
   — those are about making what we plot honest, and are validated by this wave working at all
   (PIT backfill + block bootstrap ran clean on the existing engine). The doctrine survives
   even though the prediction thesis is weak — precisely the §6.1 outcome.

**Net: REFINE the program toward risk-lens + measurement + regime context; do NOT build a
position/phase return-prediction engine.** Carry the hazard/conditional stack as a
research-gated surface behind DL-1/DL-2, not as a v1 sizing input.

---

## 5 · Spec problems found in D2 / D5 while building

- **D5 §1.7 / D2 §4.1 assume the drawdown-lens ordering (DECLINE>FRESH-BUY) is a stable
  calibration input.** It is not — it does not survive PIT + month-block bootstrap on the
  membership-free universe (§2.3). D2-W6 / D5-W2 must treat `ladder_calibration.json`'s
  endpoint-return ordering as an **unvalidated observation**, and BC-1's success criterion
  (train→holdout rank-corr > 0.5 on the risk-adjusted metric) is likely to **fail** — which is
  the correct, pre-registered outcome, but the wave prompts should not presuppose it passes.
- **D2 §4.1's `score_metric = mean_fwd_ret / |dd_p10|` is dominated by the denominator.** In
  this study the dd-adj ordering is driven almost entirely by *which states sit in deeper
  drawdowns* (a volatility fact), not by return. The metric conflates "low tail risk" with
  "good state." D2-W6 should either (a) fit the return and risk channels separately (doctrine
  #9 already wants risk isolated), or (b) residualize dd-adj on realized vol before ranking
  states — else it will "discover" that low-vol = high-position states score best, which is
  mechanical, not predictive.
- **D5 §1.8 cone-coverage nominal is 50% (S∈[0.25,0.75]); the phase wheel has zero
  hysteresis (D1, noted).** This study confirms the hysteresis gap matters for grading: a phase
  that flips on a one-week MACD wobble pollutes any phase-conditioned forward statistic. The
  Peak/Trough DD asymmetry would likely sharpen with the D1 hysteresis fix in place — **W1.2's
  hysteresis should land before W2.4 grades phase-conditioned promises**, or the phase graders
  inherit the wobble noise this study had to average through.
- **Month-end cadence (D2 §1.4) is confirmed correct** — at 21d horizon the month-block
  bootstrap gives `n_eff ≈ n_months` with no overlap deflator needed; at 63/126d the windows
  overlap and the **month-block resampling (not row resampling) is load-bearing** — a row
  bootstrap here would have understated every CI by the 2.4–6× the audit warned of, and would
  have falsely "confirmed" the Peak DD signal post-2018.

---

## 6 · Reproduce

```
python -m scripts.keystone_position_gate_phase0            # full study (~15-17 min)
python -m scripts.keystone_position_gate_phase0 --verify   # PIT spot-checks only
python -m scripts.keystone_position_gate_phase0 --quick    # smoke (2022+ slice)
```

Artifacts (committed, `data/research/keystone_tr0/`): `backfill.parquet` (0.53 MB, 8,344 PIT
stamps + forward outcomes), `study_tables.json` (full / pre_2018 / post_2018 decile/phase/
timing/signal/inversion tables + CIs), `manifest.json` (provenance + PIT checks). Basis `tr`,
epoch `tr_v0`, research-only.

---

## Status log

- 2026-07-02 — W0.4 shipped. Keystone verdict: **position = NO-EDGE; phase = risk-only,
  regime-fragile drawdown signal (inverted sign); ladder inversion NOT confirmed
  (INCONCLUSIVE).** PIT invariance verified. `PREREGISTRATION.md` ledger created with all
  downstream gates + BH-FDR budget. Program steer: REFINE toward risk-lens + measurement +
  regime context; hazard/conditional stack carried as a decision-gated research surface.
