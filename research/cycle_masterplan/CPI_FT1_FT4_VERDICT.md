# CPI FT-1 / FT-4 — BINDING VERDICT (first CPI discovery batch)

**Run date:** 2026-07-06 · **Branch:** feat/cycle-pattern-p3-ft · **Gates:** PREREGISTRATION.md §12
(frozen in the criteria commit BEFORE this run; git history shows the freeze) · **Family:**
`cycle_pattern_ft`, BH-FDR q=0.10 across 12 cells · **Budget:** `rf.cycle_pattern.ft_v0` n=12,
declared pre-p-value in `data/trial_ledger.jsonl` · **Artifacts:**
`data/cycle_pattern/ft_trials/ft1_breadth.json`, `ft4_structure.json`.

---

## 0 · TL;DR

**Both frozen covariate blocks FAIL — 0 of 12 cells pass.** Adding family breadth (FT-1) or
cross-entity structure (FT-4) to the shipped W2.5-bound hazard feature set does not improve
out-of-sample turn-hazard Brier under the identical W4.2 harness (2010–2023 test years, embargo
< 2024-01-01 preserved). One cell is *significantly harmful*: the breadth block degrades **down/1m**
— the strongest shipped cell — by ΔBrier −0.0056 (CI₉₀ [−0.0099, −0.0016]). Neither block enters the
shipped model. Null truths **CPI-016** and **CPI-017** are appended to the truth registry; reopening
requires a new preregistered trial naming the null (dead-stays-dead).

This is the CPI information program doing its job on batch one: the covariate-expansion thesis
(masterplan §4) is not falsified — *these two specific blocks under this specific harness* are.

## 1 · What was tested (frozen, verbatim §12)

- **FT-1 breadth block:** `fam_pct_above_200d`, `fam_pct_above_50d`, `breadth_div_own`,
  `breadth_thrust_3m` — PIT-pure from member tapes (loader reconciles with the panel's own
  `trend_pass` family-mean at corr 0.977).
- **FT-4 structure block:** `sync_family` (W5.1 statistic), `phase_breadth_late`,
  `phase_breadth_early`, `pos_dispersion` — PIT-pure from the panel cross-section.
- **Baseline:** the shipped feature set refit under identical expanding annual folds inside the same
  runner (not the KM prior) — the bar was "add information beyond what ships."
- Panel `price_c4414dcb`, 16,429 rows after embargo truncation, 14 test years (2010–2023),
  leak-free out-of-fold PAV calibration, paired ΔBrier month-block bootstrap (800, seed 7).

## 2 · Ledger (full tables in the JSON artifacts)

| cell | ΔBrier (base − base+X) | CI₉₀ | years+ /14 | BH | verdict |
|---|---|---|---|---|---|
| FT1 up/1m | +0.0026 | [−0.0005, +0.0057] | 10 | ✗ | FAIL |
| FT1 up/3m | +0.0028 | [−0.0004, +0.0060] | 7 | ✗ | FAIL |
| FT1 up/6m | +0.0021 | [−0.0003, +0.0046] | 8 | ✗ | FAIL |
| FT1 dn/1m | **−0.0056** | **[−0.0099, −0.0016]** | 4 | ✗ | **FAIL (harmful)** |
| FT1 dn/3m | −0.0018 | [−0.0041, +0.0003] | 7 | ✗ | FAIL |
| FT1 dn/6m | −0.0006 | [−0.0014, +0.0003] | 6 | ✗ | FAIL |
| FT4 up/1m | −0.0018 | [−0.0058, +0.0023] | 8 | ✗ | FAIL |
| FT4 up/3m | −0.0019 | [−0.0070, +0.0030] | 7 | ✗ | FAIL |
| FT4 up/6m | −0.0036 | [−0.0077, +0.0003] | 8 | ✗ | FAIL |
| FT4 dn/1m | −0.0014 | [−0.0051, +0.0022] | 9 | ✗ | FAIL |
| FT4 dn/3m | +0.0000 | [−0.0023, +0.0024] | 7 | ✗ | FAIL |
| FT4 dn/6m | +0.0010 | [−0.0000, +0.0020] | 6 | ✗ | FAIL |

## 3 · Honest reading (adjudication, not criteria-bending)

1. **The up-side breadth lean is real but unearned.** All three FT-1 up cells are positive with lower
   CI bounds a hair below zero, and up/1m printed 10/14 positive years. Under the frozen gate this is
   FAIL, and it ships as FAIL. It is recorded in CPI-016's falsifier: a future preregistered
   re-trial (more accrual, or a peak-direction-only block with fewer parameters) is the legitimate
   reopening path. No score, no display, no language change may cite the lean meanwhile.
2. **Breadth harms trough-hazard at 1m.** The most robust shipped cell (down/1m PASS in W4.2) gets
   *worse* when four correlated breadth features are added — classic variance cost where events are
   sparse. Consequence beyond this trial: future FT blocks should default to **direction-scoped**
   registration (a block may enter one direction's model only), and small blocks beat kitchen sinks.
3. **Cross-entity structure adds nothing at the instrument level.** Sync/dispersion/phase-breadth as
   *features on member hazards* is now a paid-for null. This does NOT test the masterplan's C5 use of
   the same aggregates — predicting the **index-level** turn from constituent structure (IX-1) is a
   different target with its own registered gate, and remains open.
4. **Method note.** The FT-4 cross-section statistic was computed direction-pooled per (family, date)
   and broadcast to rows — the natural reading of §12; recorded here for reproducibility.

## 4 · Program steer

- FT-2 (credit/curve) and FT-3 (liquidity) remain the next registered blocks — macro-priced series
  are more orthogonal to the panel's price-derived features than breadth proved to be. Register them
  direction-scoped and small (≤3 features).
- The lattice batch (family `cycle_pattern_lattice`) proceeds unchanged — it targets *conditional
  cells* (drawdown tail, persistence, false-repair), not hazard-model uplift.
- IX-1 (index-level turn hazard from constituent structure) is unaffected by FT-4's null and stays on
  the P4 docket.

## 5 · Reproduce

```
python3 scripts/build_cycle_pattern_ft_phase0.py            # full run, ~30s, deterministic (seed 7)
python3 -m pytest tests/test_cycle_pattern_ft_phase0.py -q  # frozen-block + gate-math guards
```
