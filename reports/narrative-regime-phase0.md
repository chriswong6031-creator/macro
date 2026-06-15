# Narrative-Dominance Index — Gate A (Phase-0)

**Verdict: NO-GO for a scored leg → DISPLAY-ONLY.** Reproduce: `python scripts/narrative_regime_phase0.py`

## The question

The narrative-quantification framework's P1 hinges on one test: does the **text-uncertainty
signal** (EPU + GPR-threat) add **forward-realized-volatility** predictive content that is
**incremental over VIX**? If not, a Narrative-Dominance Index (NDI) vol leg is redundant with
the dashboard's existing vol zoo (`vrp`, `vix_term`, `drawdown_risk`, MRS, turbulence, GEX) and
must **not** become a scored conditioner — it ships as a display banner only.

## Setup

- **36 years, daily, 1990-01-02 → 2026-06-12 (9,179 obs)** — far deeper than the 2023+ stock-cache
  window, because EPU/GPR/VIX/SPX are all deep macro series.
- Signal `TU` = mean of expanding-z(log EPU), expanding-z(log GPR-threat) — **PIT** (expanding
  stats, no look-ahead).
- Target = forward realized vol `RVfwd(h)` over *t+1..t+h*, h ∈ {5, 10, 21, 63}.
- Baseline = VIX (VIXCLS) + trailing realized vol `RVnow(21)`.
- Incremental IC = Spearman(TU, residual of `RVfwd ~ VIX + RVnow`); significance by **block
  bootstrap** (block=63, B=2000 — overlapping forward windows autocorrelate, so naive t is
  inflated); **BH-FDR** across horizons; **split-half** sign-stability.

## Results

| h | raw IC(TU) | IC(VIX) | **incremental IC(TU \| VIX, RVnow)** | 90% CI | FDR q | half-split |
|---|---|---|---|---|---|---|
| 5  | +0.106 | +0.671 | **−0.064** | [−0.106, −0.019] | 0.022 ✔reject | −0.029 / −0.093 |
| 10 | +0.102 | +0.725 | **−0.084** | [−0.130, −0.032] | 0.012 ✔reject | −0.063 / −0.107 |
| 21 | +0.098 | +0.732 | **−0.088** | [−0.141, −0.029] | 0.021 ✔reject | −0.088 / −0.096 |
| 63 | +0.062 | +0.689 | **−0.129** | [−0.204, −0.057] | 0.012 ✔reject | −0.195 / −0.102 |

TU vs VIX rank-corr = +0.179.

## Reading

1. **Raw text-uncertainty does read forward vol** (raw IC +0.06 to +0.11) — consistent with the
   EPU/GPR literature. Taken alone it looks useful.
2. **VIX dominates** (IC +0.67 to +0.73). It is a far stronger forward-vol predictor.
3. **Incremental over VIX, text-uncertainty is significantly *negative*** at every horizon — the
   bootstrap CI excludes zero on the wrong side, all four FDR-reject, and the sign is stable
   across both halves of the sample. Once VIX (and current realized vol) are controlled, residual
   policy/geo text-uncertainty is *mildly contrarian* for forward vol: elevated narrative noise
   **without** a corresponding VIX move tends to precede **lower** realized vol — the scare that
   doesn't materialize beyond what VIX already priced.

## Decision

- **NDI is REDUNDANT-or-worse with VIX for volatility.** It does not earn a scored leg. Ship the
  NDI as a **display banner** (`engine/narrative_regime.py`), with `gate_multiplier` **pinned to
  1.0** (no-op). **Do not build the P2 subtract-only scored gate** — the premise (text-narrative
  vol carries content beyond VIX) is empirically false here.
- Gate B (does narrative-driven vol degrade *signals* more than plain high-VIX) is **moot**: with
  no incremental forward-vol content over VIX, gating existing signals on TU rather than VIX is
  unjustified. Not run.
- This joins the dashboard's honest-negative ledger (commodity-carry, MACRO_RISK B-1, base-scanner,
  rvol, short-interest): validated, then **display-only**, never scored.

## What survives

The **display** value is real and crowding-proof precisely because it is not sold as alpha: a
neutral percentile read of how elevated policy/geopolitical narrative uncertainty is, with the
GPR **threat/act** split (the one published-validated reversibility tag — threats revert ~3mo,
acts persist) shown as context. The genuinely hard-to-replicate asset remains the forward PIT
event accrual (`data/news_vector/events.parquet`), not any directional or vol claim here.
