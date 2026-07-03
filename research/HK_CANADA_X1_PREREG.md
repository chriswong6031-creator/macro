# X1 — A-Twin Read-Through — PRE-REGISTRATION

**Battery:** X1 (HK & Canada masterplan §3; new mechanism appended to trial ledger §6.1).
**Grade (honest prior):** mechanism-strong, n-limited (25 pairs). GO needs the *pooled*
panel to carry it. Could be the program's first GO — the gates hold anyway.
**Pre-registered by:** quant research agent (Opus). **Committed BEFORE any run** — the
commit timestamp is the audit trail. Nothing below is wired into any live engine, board,
or composite (masterplan W-pre acceptance: reports only).

---

## 0. One-sentence thesis

The A-share **twin** of a dual-listed A/H name carries VALIDATED in-house state (A-side
within-history 3-month reversal: +0.56%/mo, Sharpe 0.58 — `reports/china-reversal-phase0`;
`washout_2w`). Because the A and H investor bases are **segmented** (Connect quotas,
capital controls, different marginal buyers), the A-side can discover China-local
information before it is impounded in the H leg. **Does the A-twin's state predict the
H-share's forward excess return over the HSI, incrementally to the H-leg's own trailing
return?**

This is a **cross-market read-through / cross-sectional-ranking** claim. It is *distinct*
from H3 (which ranks on the A/H *premium* percentile — a relative-value level) and from H4
(H-side own reversal, which is KILLED). X1's signal is the **A leg's own price state**,
used to rank the **H leg's** forward return.

---

## 1. Why this is DSR-gated and expected borderline (pre-stated)

- **Only 25 pairs** → the cross-section is thin (deepest quintile ≈ 5 names). The A/H
  complex is one correlated HK/China basket, so cross-sectional breadth adds signal but
  little *independent time*; effective-N is time-like (block-bootstrap t_eff), not
  25×T. Pre-stated expectation: t_eff on the order of the H3 read (≈120–140 at 3m).
- **Overlapping forward windows** serially-correlate the per-date statistics → HAC
  (Newey-West) t-stats and block-bootstrap t_eff are mandatory.
- **Segmentation is a real, dateable mechanism** (Connect launched Nov-2014 for SH,
  Dec-2016 for SZ; quotas + tax rules segment the marginal buyer) — but the read-through
  edge, if any, is a *lead-lag* that arbitrage should compress. Honest prior: the H leg
  may already impound A-side info within days (H4's kill is consistent with H-side price
  state being efficient), so the read-through survives ONLY if the A-side carries
  *incremental* information the H price has not yet reflected. That is the whole test.
- **Program multiplicity** is controlled at the program budget via the ledger-fed DSR:
  `TrialLedger.with_declared_budget(36, "hkca_x1")` (masterplan §9: program budget now
  ≈36, counting every config across both markets and all batteries; X1 is a new family so
  it declares the *current program budget* as its haircut floor — the conservative
  direction). The 3 pre-registered trials below are one FDR family.

---

## 2. Data (exact, PIT, suspension-honest)

All read from the session worktree absolute path (data is gitignored/R2; not in this
isolated worktree):

- **A closes:** `data/china_stocks/<A>.parquet` (OHLCV; `close`; deep 1993–2008→ per name,
  fresh to 2026-07-03). Provenance: China vendor (akshare/tushare lineage). **Total-return
  vs price adjustment is NOT asserted** — treated as a price-state proxy; the A signal is a
  *within-pair-history z / percentile of a trailing return*, which is invariant to a
  constant multiplicative TR drift over the lookback, so the ranking is robust to the
  adjustment question. (Stated as a caveat, §9.)
- **H closes:** `data/hk_stocks/<H>.parquet` (OHLCV; `close`; deep 2000–2005→ per name,
  fresh to 2026-07-03). H-leg forward returns are dividend-adjusted TR (memory: Yahoo
  `close` is TR); HSI is a price index → the same TR-vs-price benchmark mismatch H3
  flagged applies. Mitigation: the **dividend-neutral A-vs-H long/short** and the
  **rank-IC** (drift-free) are the binding legs; the top-N long-only excess carries a
  positive dividend drift and is reported as corroboration, not the decision leg.
- **HSI benchmark:** `data/hk/_HSI.parquet` `close` (1986→2026, price index).
- **Pairs:** `data/hk_ah_panel/pairs.json` (25 verified pairs, per-pair `joint_start`).
- **Premium (for the H3-interaction control, trial c):** `data/hk_ah_panel/premium.parquet`
  (log A/H premium, daily, 25 cols keyed by H-ticker; higher = H cheaper).

**Suspension / halt rule (binding, every forward return):** entry = the first REAL H close
strictly after the rebalance date t; if no valid H print exists within **5 sessions** after
t the name is EXCLUDED that rebalance (no forward-fill across halts). Horizon-end close must
be a real print. HSI excess measured over the SAME entry→exit calendar span from real
closes only. (Reuses the H3 `fwd_excess` construction verbatim — same halt guard.)

**Fills:** next-valid-CLOSE (HK `open` column is the panel-wide established-unpopulated
precedent; A signals are formed on close at t, H entry on the next H close — a full session
of implementation lag, so no look-ahead: the A state at t's close is public before the H
entry close on t+1).

---

## 3. The signal constructions (exact, frozen)

Signals are formed **at each month-end t** on data through t's close, per H-ticker (indexed
by its A-twin's series). Forward returns are the H leg's excess over HSI from the next H
close.

**Trial (a) — A-twin 3M reversal read-through (PRIMARY).**
Let `rA_3m(t)` = the A leg's trailing ~63-trading-day return ending at t. The reversal
signal is the **within-pair-history z-score** of `rA_3m`, sign-flipped so deep-negative
(A-washout) ranks HIGH (long candidate):
`sigA_rev(t) = − zscore_own( rA_3m ; window=504, min=252 )`
where `zscore_own` is `(x_t − mean(trailing 504)) / std(trailing 504)`, min 252 non-NaN.
Rationale: the validated A-side edge is *within-history 3M reversal, deepest, no gates*
(`china-reversal-phase0`). Deep-negative A 3M return = washout = the A-side long fuel; X1
asks whether that fuel is **not yet** in the H price. Binding horizon **3m** (the horizon
the A edge is strongest at); **1m** reported as the second horizon for sign-stability.

**Trial (b) — A-twin 1M momentum lead (short-horizon discovery).**
`sigA_mom1m(t) = zscore_own( rA_1m ; window=504, min=252 )`, `rA_1m` = trailing ~21d A
return. Hypothesis: at a SHORT horizon the A leg *leads* the H leg (A discovers
China-local info first; H follows), so recent A strength → H catches up. Binding horizon
**2–6w** (implemented as **h=21 trading days**, ~1m — the closest single clean bar to the
"2–6w" band; 10 sessions / ~2w reported as the second horizon). Note the SIGN is opposite
to (a): (a) is reversal (contrarian on the A 3M level), (b) is momentum (continuation of
the A 1M move into H). Pre-stated: if BOTH fire with these opposite signs that is a
horizon-consistent lead-lag story; if they contradict at the same horizon, neither is a
clean mechanism.

**Trial (c) — DOUBLE-CHEAP interaction (SUBSET cell, lower n — pre-stated).**
The candidate "about to run" cell = A-washout AND H-discount-extreme simultaneously.
`sigA_rev` high (top-tercile within the cross-section that month) **AND** the H3 premium
own-history percentile `prem_pctile(t)` high (top-tercile; H unusually cheap vs its A).
Test = the forward 3m excess of names in the **double-cheap** cell vs (i) A-washout-only,
(ii) H-discount-only, (iii) the panel mean. This is explicitly a **subset** with fewer
name-months; pre-registered as lower-power. Its verdict is capped at ACCRUE regardless of
point estimate (a subset-of-a-subset cannot earn GO at this n — pre-stated per §8).
`prem_pctile` reuses H3's `own_pctile` (window 504, min 252) on `premium.parquet`.

**Cross-section, weighting, portfolio:** monthly rebalance (`resample("ME").last()`);
require **≥8 pairs** with a valid signal AND a fillable forward return that month (the H3
min-pairs floor). Long = **top-5** H legs by signal (equal-weight); rank-IC computed on
the full valid cross-section each month. Long/short (dividend-neutral) = top-5 minus
bottom-5, both H legs.

---

## 4. Controls (incremental-value tests — binding for the verdict)

The read-through must be **incremental to the H-side's own price state** (H-side reversal
/ momentum is DEAD/KILLED per H4 — so any X1 edge is orthogonal to a dead factor; we state
and TEST that orthogonality rather than assume it):

- **C1 — H own trailing return control.** Residualize `sigA_rev` (and `sigA_mom1m`) each
  rebalance against the H leg's OWN matched trailing return (`rH_3m` for the 3m trial,
  `rH_1m` for the 1m trial), cross-sectionally (`cross_sectional_resid`). Report the
  **residual rank-IC** alongside raw. Binding: the residual IC must keep its sign and
  ≥~50% of raw magnitude, else the "read-through" is just the H leg's own (dead) price
  state re-expressed. This is THE key control.
- **C2 — FX control.** The A leg is CNY, H leg is HKD, premium embeds CNH/HKD. Include the
  trailing CNH-move as a second residualization basis for the primary (reported; a
  read-through that is only an FX carry is not a name-level edge). CNH proxy: if a clean
  in-tree CNH/USDHKD series is unavailable at build, state that and fall back to
  residualizing against the **premium level** (which mechanically embeds the FX gap) —
  this subsumes the FX confound and is stated as the substitute.
- **C3 — premium-level control.** Residualize `sigA_rev` against the CONTEMPORANEOUS A/H
  premium own-history percentile, so X1's A-state edge is shown incremental to H3's
  premium edge (they must not be the same tilt wearing two hats). Report residual IC.

Controls are **reported diagnostics that gate the verdict** (C1 binding; C2/C3 reported),
not separate FDR trials.

---

## 5. Statistics (constitution §6, binding)

For each of the 3 trials at its binding horizon:
1. **rank-IC** time series (`rank_ic` per month) → `ic_summary` (mean IC, IC-IR, HAC-t).
2. **HAC (Newey-West) t-stat** on the monthly top-5 long-only excess AND on the L/S
   series (`newey_west_tstat`, lags=3 for 3m overlap / lags=1 for 1m).
3. **BH-FDR** across the family (the p-values of the 3 trials' binding-horizon excess +
   the two secondary-horizon reads; α=0.10; `benjamini_hochberg`).
4. **DSR** via `deflated_sharpe(..., ledger=TrialLedger.with_declared_budget(36,
   "hkca_x1"), family="hkca_x1", t_eff=<block-bootstrap>)` on the binding-horizon excess.
   `t_eff` from `bootstrap_effective_t` (block=21, monthly returns → block on the daily
   L/S return series where available, else the monthly-return block).
5. **Split-half sign stability** (median-date split) + **era split** (pre/post 2016-12,
   the Shenzhen-Connect segmentation break) — sign must not flip.
6. **Effective-N** = block-bootstrap t_eff (independent-episode / time-like), reported.
7. **Survivorship bound:** the 25 pairs are today's survivors → biased up. Bound =
   (i) drop the 5 shortest-history pairs; (ii) deep-core ≥12y pairs. Report the edge under
   both haircuts. Reported IC is an **upper bound** (no PIT dual-listing delisting
   registry in-tree).

---

## 6. Trial ledger (this battery, frozen — one family "hkca_x1")

| # | trial | signal | binding horizon | 2nd horizon | verdict cap |
|---|---|---|---|---|---|
| a | A-twin 3M reversal read-through (PRIMARY) | `−zscore_own(rA_3m,504)` | 3m (63d) | 1m (21d) | GO possible |
| b | A-twin 1M momentum lead | `+zscore_own(rA_1m,504)` | ~1m (21d) | ~2w (10d) | GO possible |
| c | double-cheap interaction (A-washout ∧ H-discount) | tercile∧tercile cell | 3m (63d) | — | **ACCRUE max** |

Program DSR haircut floor: **36** (`with_declared_budget(36,"hkca_x1")`). All A/H-panel /
china-reversal research variants already counted in the program budget; X1 adds no
lowballing. The registry entry is appended at the END of the experiments array; NO WIRING.

---

## 7. Gates (constitution — a trial is GO only if ALL pass at binding horizon)

1. **rank-IC > 0** at BOTH the binding and second horizon, SAME sign.
2. **HAC-t ≥ 2.0** on the binding-horizon top-5 excess AND on the L/S series.
3. **BH-FDR reject** (q ≤ 0.10) within the family on the binding-horizon excess p.
4. **DSR ≥ 0.90** on the binding-horizon excess, ledger budget 36, t_eff-corrected.
5. **Split-half AND era sign stability** (no flip).
6. **C1 incremental control:** residual-vs-H-own-return IC keeps sign and ≥50% of raw
   magnitude (the read-through is not the dead H-side factor relabeled).
7. **Survivorship bound:** edge survives both haircuts (does not vanish / flip).

---

## 8. Pre-stated verdict rules (honest defaults, no torture)

- **All 7 gates pass** on trial (a) or (b) → **GO** (the program's first). Report it plainly
  with the survivorship bound as the stated ceiling.
- **rank-IC>0 both horizons, HAC-t ≥ 1.5 at binding, FDR-reject, BUT DSR < 0.90** → **ACCRUE
  — near-GO** (the H3 outcome shape; the honest expected landing at n=25).
- **C1 control fails** (residual IC flips or collapses < 50%) → **NO-GO** (the apparent
  read-through was the H leg's own dead price state; report the kill).
- **HAC-t < 1.5 OR IC sign-flips across horizons/eras** → **NO-GO**.
- **Trial (c)** is capped at **ACCRUE** by construction (subset-of-subset, lower n): a
  strong point estimate is reported as *suggestive of the double-cheap cell*, never GO.
- DSR = 0.88–0.899 is **ACCRUE**, not GO. No rounding up. NO-GO / ACCRUE are respectable.

---

## 9. What this will NOT show (pre-committed)

- **No causal** segmentation-lead mechanism — a cross-sectional association between A-state
  and H-forward, confounded with the shared China/HK beta, sector, size, and the same
  2024–2026 southbound dividend-tax cycle that confounds H3.
- **No true PIT market cap / size control** (none in-tree; fundamentals static) — a size
  bet cannot be fully ruled out; the C1 (H-own-return) and C3 (premium) controls bound but
  do not eliminate it.
- **No delisting-survivorship correction** — reported IC is an UPPER bound (§5.7).
- **A-close adjustment (TR vs price) unasserted** — mitigated by the within-history-z
  transform (invariant to constant drift) but a non-constant adjustment could bias the z.
- **TR-vs-price benchmark mismatch** (H legs TR, HSI price) — the dividend-neutral L/S and
  the rank-IC are the drift-free binding legs; long-only excess carries a positive drift.
- **Only 25 names, one correlated basket** — cross-sectional breadth is not independent
  time; t_eff (not n×T) is the honest sample. GO here is an *edge candidate on the deepest
  matched panel we have*, not an institutional-grade claim.

Code: `research/hk_x1_atwin_readthrough.py`. Report: `reports/hkca-x1-phase0.md`. Raw:
`research/hk_x1_results.json`.
