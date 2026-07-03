# W5.1 Lead-Lag Phase-0 — STOP · NO-GO Verdict

**Wave:** W5.1 · **Date:** 2026-07-03 · **Outcome:** STOP — do not build the interaction layer

> **The one-sentence result:** Stage A found 136 in-sample FDR survivors, but Stage B
> showed zero out-of-sample Brier improvement (rel improvement = 0.029%, CI₉₀ spanning
> zero, only 3 of 9 year-blocks positive) — all three LL-B sub-criteria fail.
> The STOP fallback deliverable is the sync gauge, now live on measurement.html.

---

## Two-commit integrity record

| commit | content | sha prefix |
|---|---|---|
| commit 1/2 | frozen protocol (`scripts/leadlag_phase0.py` + `W51_LEADLAG_PROTOCOL.md` + preregistered criteria in `leadlag_phase0.json`) | `8a39244` |
| commit 2/2 | results (`leadlag_phase0.json` filled, `data/leadlag/*`, this verdict, prereg update, sync gauge) | this commit |

The criteria in `preregistration` block of `leadlag_phase0.json` were **not modified**
after the run. `note` in the results JSON reads: _"RESULTS COMMIT — criteria in
`preregistration` were NOT moved."_

---

## Stage A: In-sample screening (≤2017 train)

**Protocol:** cross-lagged Δpos correlation for all within-family instrument pairs at lags
1–6 months; block-bootstrap null band (n_boot=2000, block=1 month, seed=7); BH-FDR at
q=0.10 across all 8,253 pair×lag combinations.

**Universe:** 66 instruments (11 US sector ETFs, 24 country ETFs, 31 CN Shenwan sectors);
7 mechanical bloc composites excluded per A14.

**Results:**

- Total pair×lag tests: **8,253**
- FDR survivors (q=0.10): **136**
- LL-A criterion met: **YES** (≥1 survivor required)
- `gate.LL_A_pass = true`

The 136 survivors are dominated by CN-sector pairs (heavily 801950 → lagged followers at
lag 5, plus 801710/730/740/770/880/890 → various followers at lags 1 and 6); 7 country
pairs also survived (EIDO/EPOL/EWD/EWJ as leaders into European ETFs).

**Top-20 pairs selected for Stage B (by in-sample |r|, ranked):**

| rank | pair | lag | r | n |
|---|---|---|---|---|
| 1 | cn_sector 801950→801180 | 5 | 0.784 | 25 |
| 2 | cn_sector 801950→801210 | 5 | 0.754 | 25 |
| 3 | cn_sector 801950→801010 | 5 | 0.735 | 25 |
| 4 | cn_sector 801950→801030 | 5 | 0.734 | 25 |
| 5 | cn_sector 801950→801130 | 5 | 0.732 | 25 |
| 6 | cn_sector 801950→801140 | 5 | 0.715 | 25 |
| 7 | cn_sector 801950→801150 | 5 | 0.681 | 25 |
| 8 | cn_sector 801950→801230 | 5 | 0.681 | 25 |
| 9 | cn_sector 801950→801080 | 5 | 0.678 | 25 |
| 10 | cn_sector 801890→801130 | 6 | 0.660 | 24 |
| 11 | cn_sector 801730→801130 | 6 | 0.651 | 24 |
| 12 | cn_sector 801950→801200 | 5 | 0.649 | 25 |
| 13 | cn_sector 801880→801130 | 6 | 0.643 | 24 |
| 14 | cn_sector 801950→801120 | 5 | 0.641 | 25 |
| 15 | cn_sector 801950→801110 | 5 | 0.640 | 25 |
| 16 | cn_sector 801890→801180 | 6 | 0.634 | 24 |
| 17 | cn_sector 801880→801180 | 6 | 0.633 | 24 |
| 18 | cn_sector 801710→801130 | 6 | 0.631 | 24 |
| 19 | cn_sector 801710→801080 | 6 | 0.630 | 24 |
| 20 | cn_sector 801730→801180 | 6 | 0.626 | 24 |

These 20 pairs are persisted in `data/leadlag/frozen_pairs.json`.

---

## Stage B: OOS Brier evaluation (2018–2026, walk-forward)

**Protocol:** for each frozen pair, at each OOS month t, compute whether the follower
turns within 3 months (binary outcome); construct `leader_turned_3m` feature gated on
`confirmed_at ≤ t` (the confirmed_at discipline — see below); fit a logistic hazard and
evaluate Brier score vs the no-leader baseline. Pool across all pair×month observations.

**OOS observations:** 2,040 (n = 20 pairs × ~102 months 2018–2026)

**Pooled results:**

| metric | value | bar |
|---|---|---|
| Brier (baseline, no leader) | 0.28668 | — |
| Brier (with leader feature) | 0.28660 | — |
| Relative Brier improvement | **+0.029%** | ≥ 2.0% |
| 90% CI on ΔBrier | [−0.261%, +0.288%] | excludes 0 |
| Year-blocks positive (n=9) | **3 of 9** | ≥ 6 of 9 (≥2/3) |

**All three LL-B sub-criteria FAIL:**

- `rel_ok = false`: 0.029% << 2% bar
- `year_blocks_ok = false`: 3/9 positive << bar of 6/9
- `ci_excludes_0 = false`: CI spans −0.261% to +0.288%, includes zero

`gate.LL_B_pass = false` · `gate.LL_B_detail = {rel_ok: false, year_blocks_ok: false, ci_excludes_0: false}`

**Per-pair breakdown (selected):**

| pair | lag | rel_improvement | leader_feat_active_frac |
|---|---|---|---|
| 801950→801180 | 5 | +3.17% | 12.4% |
| 801950→801150 | 5 | +5.62% | 12.4% |
| 801710→801080 | 6 | +5.50% | 19.3% |
| 801950→801200 | 5 | +4.83% | 12.4% |
| 801950→801120 | 5 | +3.13% | 12.4% |
| 801880→801180 | 6 | +0.81% | 17.8% |
| 801950→801010 | 5 | −0.16% | 12.4% |
| 801950→801210 | 5 | −3.10% | 12.4% |
| 801950→801140 | 5 | −3.55% | 12.4% |
| 801880→801130 | 6 | −4.69% | 17.8% |
| 801730→801180 | 6 | −2.99% | 21.1% |

The feature fires infrequently (~12–21% of OOS months), consistent with the protocol's
3-month recency window after a confirmed leader turn. The few pairs with positive
improvement do not survive at the pooled level: their contributions are cancelled by
equally-sized losses in other pairs, and the CI symmetrically spans zero.

---

## Confirmed_at discipline: how the code enforced it

The preregistration states: _"leads keyed on pivot dates (event_date) are FORBIDDEN — they
leak the future."_ The enforcement in `scripts/leadlag_phase0.py`:

1. `load_confirmed_turns()` reads the persisted turn archive and **filters out all turns
   where `provisional == True`** (open unconfirmed legs whose final direction is unknown).
2. `_leader_turned_feature(panel, leader_id, turns)` evaluates, for each follower decision
   date `t`, whether the leader has a turn with `confirmed_at ≤ t` **and** the turn is
   within `LEADER_TURN_WINDOW_M=3` months before `t`. If `confirmed_at > t` — even if the
   pivot date (event_date) precedes `t` — the feature returns 0. The pivot date never
   enters the gate.
3. Verified by `tests/test_leadlag_phase0.py::test_late_confirmation_no_lead`:
   a synthetic leader pivots at 2015-05-15 but confirms on 2015-09-20; the follower's
   decision is 2015-06-30. The feature must return 0 (confirmed after the decision). The
   test asserts this contract and is passing.

No lookahead: the interaction layer cannot be built using a signal that will be known only
at a future date.

---

## Runtime

534 seconds (8.9 minutes). Dominated by the block-bootstrap null band computation over
8,253 pair×lag tests (n_boot=2000, block=1 month).

---

## Verdict and stop action

```
gate.LL_A_pass = true
gate.LL_B_pass = false
gate.verdict   = "NO-GO"
gate.stop_action = "ship_sync_gauge"
```

**Decision:** do not build the lead-lag interaction layer. Stage A found statistically
significant in-sample cross-correlations, but OOS predictive power is indistinguishable
from zero. The pattern is consistent with overfitting to slow-moving mean-reversion in
China sector phase cycles, which looks like "leading" in-sample but does not generalize.

**Fallback deliverable shipped (T7 / STOP rule):** the sync gauge
(`data/leadlag/sync_gauge.json`, rendered on `measurement.html`) is the measured,
honest replacement for markets.html's fake convergence bands. It reports cross-sectional
pos_v2 dispersion per family with its full history — a conditioning state, not a
prediction.

---

*Artifact paths:*
- `data/cycle_hazard/leadlag_phase0.json` — full results JSON (schema: leadlag_phase0/v1)
- `data/leadlag/frozen_pairs.json` — the 20 frozen top-K pairs
- `data/leadlag/sync_gauge.json` — sync history (3 families, monthly)
- `scripts/leadlag_phase0.py` — frozen protocol (commit 1/2)
- `tests/test_leadlag_phase0.py` — confirmed_at + FDR + gate arithmetic tests
