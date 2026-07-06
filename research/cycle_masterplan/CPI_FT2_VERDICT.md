# CPI FT-2 (credit/curve) — BINDING VERDICT (second CPI discovery batch)

**Run date:** 2026-07-06 · **Branch:** feat/cycle-pattern-p3b · **Gates:** PREREGISTRATION.md §13
(frozen in the criteria commit before the run) · **Family:** `cycle_pattern_ft_v1`, BH-FDR q=0.10
across 6 cells · **Budget:** `rf.cycle_pattern.ft_v1` n=6, declared pre-p-value ·
**Artifact:** `data/cycle_pattern/ft_trials/ft2_credit.json`.

---

## 0 · TL;DR

**0 of 6 cells pass — and 4 of 6 are significantly harmful.** Adding the frozen credit/curve block
(`hy_oas_pctile`, `hy_oas_d63`, `curve_10y3m`) to the shipped hazard feature set *degrades*
out-of-sample turn prediction: every up-direction cell worsens by ΔBrier −0.0098…−0.0118 with CI₉₀
entirely below zero (years-positive only 4/14), and down/1m worsens significantly too. For scale,
the harm to up/1m (−0.0118) is nearly as large as the shipped model's entire edge over the KM prior
(+0.0140). The block is `promoted_null` (CPI-018).

## 1 · Ledger

| cell | ΔBrier (base − base+X) | CI₉₀ | years+ /14 | verdict |
|---|---|---|---|---|
| up/1m | −0.0118 | [−0.0179, −0.0064] | 4 | FAIL (harmful) |
| up/3m | −0.0113 | [−0.0179, −0.0056] | 4 | FAIL (harmful) |
| up/6m | −0.0098 | [−0.0149, −0.0050] | 4 | FAIL (harmful) |
| dn/1m | −0.0043 | [−0.0074, −0.0013] | 4 | FAIL (harmful) |
| dn/3m | −0.0020 | [−0.0041, +0.0001] | 5 | FAIL |
| dn/6m | −0.0003 | [−0.0011, +0.0006] | 7 | FAIL |

Design as frozen: W4.2 harness verbatim, baseline = shipped set refit under identical folds, embargo
< 2024-01-01, 16,429 rows, 14 test years, month-block bootstrap (800, seed 7). Features verified
non-degenerate before the run (99.9% non-null; HY OAS Δ63 range −6.4…+11.4; curve −1.88…+3.79).

## 2 · Why this happened (adjudication)

Three time-only covariates carry ~340 effective monthly observations, not 16k — and their in-sample
association with turn frequency is regime co-occurrence (e.g. 2008/2011/2020 credit spikes near
turns) that does not transport to the next test year. The L2 default cannot shrink them enough; the
expanding walk-forward exposes the failure honestly. The month-block bootstrap is what catches this
as *significant harm* rather than noise — precisely the inference discipline the ledger mandates.

## 3 · Program-level synthesis (two batches in)

18 cells registered across FT-1/FT-4/FT-2: **0 passes, 5 significantly-harmful cells, zero
criteria moved.** The consistent lesson is structural, not informational: **the pooled hazard
logistic is at capacity** — its parsimony (age structure + a few price-derived features) is
load-bearing under events-per-variable and regime nonstationarity. New information cannot enter as
"more columns on the same model."

**Steer (recorded as adjudication; §12/§13 gates stand as run):**
1. **Suspend additive-feature FT registrations on the pooled hazard.** CPI-016/017/018 falsifiers
   name the legitimate reopening conditions (structural model change, e.g. per-direction fit-level
   scoping, different regularization regime, or the regime-vintage spine).
2. Advance the docket to structurally different questions:
   - **Lattice batch 1** (`cycle_pattern_lattice`): shrunken conditional-cell estimates on the lake —
     no model fitting, immune to this failure mode.
   - **TR-1** next-phase transition model — new target, fresh capacity budget, small design.
   - **IX-1** index-level turn hazard — new unit of analysis, built small from scratch, NOT additive
     to the member-level base.
   - **Regime-v2 PIT spine** — fixes the covariate *quality* axis rather than adding quantity.

## 4 · Reproduce

```
python3 scripts/build_cycle_pattern_ft_phase0.py --batch 2   # deterministic, seed 7
python3 -m pytest tests/test_cycle_pattern_ft_phase0.py -q   # 27 guards incl. frozen FT-2 block
```
