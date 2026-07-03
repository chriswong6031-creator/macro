# W5.1 — Lead-Lag Phase-0 · FROZEN PROTOCOL (commit 1 of 2)

**This file is the protocol commit.** It is written and committed **before** any result
is computed (the two-commit discipline mandated by D5_PREDICTION.md §4 and the masterplan
§4 W5.1 row). The results commit follows separately; the git history must show the
criteria froze first. The binding gate is `research/cycle_masterplan/PREREGISTRATION.md`
§5 (LL-A / LL-B). Nothing here may be edited after the results are seen — an edit would
itself be the finding (a failed gate and a reach for the dial, per the pre-registration
doctrine).

The machine-readable frozen block lives in
`data/cycle_hazard/leadlag_phase0.json → preregistration` (emitted by
`scripts/leadlag_phase0.py --emit-protocol`).

---

## 0 · The question

The LAST gated question of the Cycle Intelligence Masterplan: **does exploitable
cross-asset lead-lag exist, or does the interaction layer STOP at a sync gauge?** A lead
is only worth building if *knowing the leader's confirmed turn improves the follower's
hazard forecast out-of-sample* — the only form in which this platform would ever use a
lead-lag (D5 §4.1).

## 1 · Universe (66 non-bloc instruments)

Ruling **A14** drops the 7 mechanical bloc composites from the panel entirely; D5 §4.2
screens ordered pairs **within** {11 US sectors}, **within** {24 countries}, **within**
{31 CN sectors}. That is `11 + 24 + 31 = 66`.

- **US sectors (11):** XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY
- **Single-country ETFs (24):** the 31 country IDs minus the 7 blocs
  {AAXJ, EEM, EFA, ILF, VGK, VPL, VXUS} → ECH EIDO EPOL EWA EWC EWD EWG EWH EWI EWJ EWL
  EWN EWP EWQ EWS EWT EWU EWW EWY EWZ EZA FXI INDA TUR
- **CN Shenwan L1 (31):** 801010 … 801980

Cross-family pairs are NOT tested (D5 §4.2 lists only within-family ordered pairs for the
screen; the 3 family-aggregate cross pairs are out of scope for this phase-0).

## 2 · Stage A — screening (TRAIN ≤ 2017-12 ONLY)

- **Statistic:** cross-correlation of monthly **Δpos** — the first difference of the
  panel's detrended oscillator `pos_osc` — because the raw osc level is near-integrated
  and would fabricate correlation; the first difference whitens it (D5 §4.2). For each
  **ordered** pair (leader → follower) at lags k ∈ {1..6} months: `corr(Δpos_leader[t−k],
  Δpos_follower[t])` on the overlapping ≥24-month TRAIN window.
- **Null band:** two-sided p per pair×lag via **circular block permutation** of the
  leader relative to the follower (block = 1 month — dates are already monthly; B=2000,
  seed=7), which preserves each series' own autocorrelation while destroying cross-series
  alignment. This is the block-bootstrap null the pre-registration names.
- **Multiplicity:** **BH-FDR at q=0.10 across ALL pairs×lags** (`grading_stats.fdr_bh`).
- **Event-study variant (confirmed_at discipline):** for each candidate pair, the
  distribution of `(follower confirmed-turn date − nearest PRIOR leader confirmed-turn
  date)`, effective-n = **number of follower turns** (EWZ has ~100+, XLC ~7 — pairs into
  low-turn followers are near-untestable and reported as such). Turns are reconstructed
  from the STRUCTURE-MATH price basis via `engine.cycle_ontology.detect_turns` (v2, with
  `confirmed_at`); **provisional open legs are excluded.**
- **Output:** the top-K = 20 pairs by screened strength (FDR survivors first, then |r|),
  frozen into `data/leadlag/frozen_pairs.json` **before** Stage B runs.

## 3 · Stage B — primary endpoint (OOS 2018 → 2026)

- For the frozen top-20 pairs only, add ONE feature to the **follower's** hazard row:
  `leader_turned_3m ∈ {0,1}` = 1 iff the leader printed a **confirmed** turn whose
  `confirmed_at ∈ (t − 3 months, t]`.
- Refit the W4.2 hazard walk-forward (`scripts/fit_cycle_hazard` design + L2 logistic +
  out-of-fold PAV isotonic) on the OOS window (`first_test_year = 2018`, train ≤ 2017 —
  the SAME cutoff Stage A froze on, 6-month embargo). Baseline = the identical design
  refit **without** the leader feature, on the same follower rows.
- **Primary endpoint:** pooled OOS **3-month** Brier of (leader model) vs (no-leader
  model).

## 4 · The gate (VERBATIM from PREREGISTRATION.md §5)

- **LL-A:** ≥1 pair×lag survives BH-FDR q=0.10 on the ≤2017 TRAIN cross-correlation.
- **LL-B:** for the frozen top-20 pairs: pooled OOS 3m Brier improvement **≥ 2%** AND
  positive in **≥ 2/3** walk-forward year-blocks AND the paired month-block bootstrap
  **90% CI on ΔBrier excludes 0**.

## 5 · STOP rule (binding, written before the run)

If Stage A yields **no** FDR survivors **OR** Stage B fails the criterion → verdict
**NO-GO: do not build the interaction layer.** Ship instead the measured
**synchronization statistic** `sync = 1 − circ_var(2π·pos/100)` per family (the mean
resultant length of the phase angles), plus the fraction of instruments in each phase
quadrant, with its full backfill history — as a MEASURED gauge on `measurement.html`,
replacing markets.html's fake convergence bands. **And stop there** (no card wiring —
that is W5.2's separately-gated decision).

If **GO**: record which pairs and what lift; do NOT wire anything into cards (W5.2's
scope).

## 6 · The integrity trap (why this study can fool itself)

A leader's turn is only usable at the follower's decision time `t` if the leader's turn
was **confirmed by `t`** (`confirmed_at ≤ t`). The panel's `event_date` is the **pivot**
date (the extremum) — which becomes knowable only *later*, when price reverses past the
ZigZag threshold. A lead measured on **pivot** dates would be a confirmation-lag artifact:
the future leaking backward, manufacturing a "lead" that could never have been traded.
Both the Stage-A event study and the Stage-B `leader_turned_3m` feature gate on
`confirmed_at`, never on the pivot. `tests/test_leadlag_phase0.py::test_late_confirmation_no_lead`
proves a synthetic leader whose turn confirms LATE cannot produce a usable lead.

## 7 · Prior expectation (disclosed, not steering the criteria)

Per masterplan §6.5, **every predictive gate in this program tested so far has FAILED**
(keystone position→return NO-EDGE; CC-1/CC-2/CC-3 turn-timing FAIL; BC-1 binding-calibration
FAIL). The pre-registration explicitly instructs that wave prompts must not assume a gate
passes. The pre-committed **likely** outcome here is **STOP + sync gauge**. The criteria
above are frozen regardless; the data decides.

## 8 · Runtime & ops

Stage A is ~66×66×6 correlations over ~200 months (trivial). Stage B is ≤20 logistic
refits (minutes). This is a **one-off research run** — it must **NOT** land in
pipeline-batch (masterplan §4 ops note). Run locally:

```
python scripts/leadlag_phase0.py --emit-protocol   # commit 1 (this protocol)
python scripts/leadlag_phase0.py --run             # commit 2 (results)
```
