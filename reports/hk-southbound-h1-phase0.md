**VERDICT: NO-GO** — southbound holding-Δ (H1). Δ4w own_pct = NO-GO; Δ1w own_pct = NO-GO. n=89 Fridays, 147-name holdings∩price panel — the delivery vehicle kills it — any faint lag+0 (disclosure-fill) signal is erased by the lag+1 render-honest fill (the red-team's execution-decay prediction), and the underlying IC is null. H1 is a positioning-CONTEXT chip, never a next-morning ranker. Signal keeps accruing; full re-run 2027-07.

Panel: 147 common names, holdings 2024-07-10→2026-07-02. Pre-reg: research/HK_CANADA_H1_PREREG.md. DSR n_trials=30 (program), cost 20bps/wk.

**Prior vs outcome:** the pre-reg's honest prior was ACCRUE-lean (positive-but-under-powered). The data came in *weaker* than that prior: the underlying rank-IC is null at Δ4w even at lag+0, and the one faint positive blip (Δ4w·1w·lag0 IC=+0.009, HAC t=1.33) is fully erased by the one-session render lag. That crosses the pre-registered NO-GO line ("lag+0→lag+1 shortfall erases the sign ⇒ context chip only"), so the honest verdict is NO-GO, not ACCRUE. Reported without torturing the blip.

## Gates vs results (IC = rank-IC on HSI-excess fwd; LS = quintile long-short)

| signal | horizon·lag | mean IC | HAC t | IC hit | LS mean%/wk | LS Sharpe(52) | DSR | split same-sign |
|---|---|---|---|---|---|---|---|---|
| d4w_own_pct | 1w·lag0 | 0.0086 | 1.3250 | 0.5680 | -0.0520 | -0.1900 | 0.0105 | yes |
| d4w_own_pct | 1w·lag1 | -0.0008 | -0.1020 | 0.4940 | -0.0970 | -0.3300 | 0.0068 | no |
| d4w_own_pct | 2w·lag0 | 0.0003 | 0.0360 | 0.5060 | -0.0080 | -0.0200 | 0.0177 | no |
| d4w_own_pct | 2w·lag1 | -0.0065 | -0.4660 | 0.4680 | -0.2800 | -0.8400 | 0.0014 | yes |
| d4w_own_pct | 4w·lag0 | -0.0021 | -0.1840 | 0.4870 | -0.0290 | -0.0600 | 0.0163 | no |
| d4w_own_pct | 4w·lag1 | -0.0072 | -0.5420 | 0.4620 | -0.2080 | -0.4300 | 0.0058 | no |
| d1w_own_pct | 1w·lag0 | -0.0090 | -1.4010 | 0.4640 | -0.3550 | -1.3800 | 0.0001 | yes |
| d1w_own_pct | 1w·lag1 | -0.0089 | -1.1090 | 0.4270 | -0.4800 | -1.7100 | 0.0000 | yes |
| d1w_own_pct | 2w·lag0 | 0.0070 | 0.9680 | 0.5830 | -0.0460 | -0.1200 | 0.0133 | no |
| d1w_own_pct | 2w·lag1 | 0.0019 | 0.2020 | 0.5490 | -0.2050 | -0.5200 | 0.0035 | no |
| d1w_own_pct | 4w·lag0 | -0.0065 | -0.9520 | 0.5190 | -0.5830 | -1.3000 | 0.0004 | yes |
| d1w_own_pct | 4w·lag1 | -0.0058 | -0.7210 | 0.4940 | -0.6300 | -1.2900 | 0.0004 | yes |

## Implementation shortfall (lag+0 disclosure fill vs lag+1 render-honest fill)

| signal | horizon | IC lag+0 | IC lag+1 | shortfall (0−1) |
|---|---|---|---|---|
| d4w_own_pct | 1w | 0.0086 | -0.0008 | 0.0094 |
| d4w_own_pct | 2w | 0.0003 | -0.0065 | 0.0068 |
| d4w_own_pct | 4w | -0.0021 | -0.0072 | 0.0051 |
| d1w_own_pct | 1w | -0.0090 | -0.0089 | -0.0001 |
| d1w_own_pct | 2w | 0.0070 | 0.0019 | 0.0051 |
| d1w_own_pct | 4w | -0.0065 | -0.0058 | -0.0007 |

## BH-FDR within H1 family (best lag+1 horizon per signal, α=0.10)

| signal | best lag+1 horizon | p_HAC | q (BH) | reject |
|---|---|---|---|---|
| d4w_own_pct | 4w | 0.5877 | 0.5877 | False |
| d1w_own_pct | 1w | 0.2676 | 0.5352 | False |

## Split-half sign stability (first vs second half of Fridays)

| signal | horizon·lag | H1 mean IC | H2 mean IC | same sign |
|---|---|---|---|---|
| d4w_own_pct | 1w·lag0 | 0.0027 | 0.0144 | yes |
| d4w_own_pct | 1w·lag1 | 0.0021 | -0.0036 | no |
| d4w_own_pct | 2w·lag0 | -0.0079 | 0.0083 | no |
| d4w_own_pct | 2w·lag1 | -0.0037 | -0.0093 | yes |
| d4w_own_pct | 4w·lag0 | 0.0016 | -0.0058 | no |
| d4w_own_pct | 4w·lag1 | 0.0080 | -0.0224 | no |
| d1w_own_pct | 1w·lag0 | -0.0167 | -0.0014 | yes |
| d1w_own_pct | 1w·lag1 | -0.0041 | -0.0136 | yes |
| d1w_own_pct | 2w·lag0 | -0.0008 | 0.0148 | no |
| d1w_own_pct | 2w·lag1 | 0.0102 | -0.0065 | no |
| d1w_own_pct | 4w·lag0 | -0.0120 | -0.0011 | yes |
| d1w_own_pct | 4w·lag1 | -0.0080 | -0.0037 | yes |

## Survivorship bound

**0 permanently-dark long-side names** across all cells over the 2-year window. The −100% dark-name imputation bound is therefore **degenerate (upper == lower)** — on a mega-cap 147-name panel over 2y, no long-side name delisted/went permanently dark. This does NOT mean survivorship risk is zero; it is **unmeasurable at this depth**. A full-power 2027 re-run on a deeper/broader panel must re-bound.

## Effective-N

Per-Friday IC count ≈ 78-85, but the independent-N is **~2 regimes** (2024-H2 China-stimulus rip; 2025→ digestion). Reported HAC t-stats and DSR are read against ~2 regimes, not the weekly count. Note also that the weekly-sampled LS series at the 2w/4w horizons *overlaps* (a 4w-forward return sampled weekly is ~4x-overlapping), so its raw T over-counts; the block-bootstrap `t_eff` and the ~2-regime framing are the honest N. Every DSR here is ≈0.01 (the LS Sharpe is negative), so this does not swing any verdict.

## Exploratory (NON-GATED): H5 peg-liquidity interaction (Δ4w, 4w horizon, lag+0)

EASY (top-tercile agg_balance, n=26) mean IC = 0.0359; TIGHT (bottom-tercile, n=26) mean IC = -0.0051. Descriptive only — no verdict, no DSR, no trial slot.

## What this does NOT show

- **Not a full-power test.** N ≈ 2 regimes; ACCRUE is the honest ceiling. The point estimates are directional colour, not a graduation.
- **Not the true Southbound universe** — mega-cap 147-name holdings∩price panel, not all ~729 Southbound names. Small/illiquid names (where demand pressure bites hardest) are absent.
- **Not survivorship-clean** beyond the (degenerate here) −100% dark-name bound.
- **Not PIT-Connect-eligibility-reconstructed** — presence-in-holdings is the eligibility proxy (PIT-honest for inclusion, not a historical roster).
- **No impact/capacity modeling**; flat 20bps/wk cost only.

_Generated by scripts/hk_h1_southbound_phase0.py — see pre-reg for the full construction._
