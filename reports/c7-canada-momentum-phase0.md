# C7 — Canada Momentum Keystone · Phase-0 IC scorecard

**Verdict: BRANCH B — ALL trials NO-GO/KILL/ACCRUE; CA board runs the ripe-list contract (§5.0) permanently, composite suppressed, tier=screen (planned outcome, not failure).**

All 4 pre-registered decision trials resolve **CA NAMES/mom_tot=ACCRUE, CA NAMES/mom_res=ACCRUE, CA SECTOR-ETFs/mom_tot=ACCRUE, CA SECTOR-ETFs/mom_res=ACCRUE**. HK-kill acceptance gate: **PASS**. No leg reaches the DSR>=0.90 / HAC-t / split-half bar; the momentum keystone does NOT support a scored rank basis for Canada on this evidence. Pre-registration: research/C7_CANADA_MOMENTUM_KEYSTONE_PREREG.md.

## Acceptance gate — reproduce the LIVE HK harness (mandatory before CA verdict)

The fork ran the HK panel through its OWN code path. **Finding:** the masterplan's pinned HK-kill numbers (mom_res LS Sharpe −0.22 full / −0.35 modern) are STALE — they were generated on the OLD 73-name HK panel. `data/hk_search/closes_deep.parquet` was since expanded to 157 names (stamped 2026-06-18), and the LIVE HK fork/base harness (`scripts/hk_residual_alpha_phase0.py`) now emits mom_res LS Sharpe **+0.17 full / +0.31 modern**. This fork reproduces that live output to <=0.02, AND reproduces the shared base `quintile_ls` on the same panel to the digit — so harness IDENTITY is proven; only the pinned reference number is stale (a data change, not a code defect). The qualitative HK verdict is UNCHANGED: residual momentum has no tradable HK edge (LS Sharpe near zero, fails DSR).

| HK panel | mom_res LS Sharpe (this fork) | live HK-fork target | stale masterplan pin | reproduces live? |
|---|--:|--:|--:|:--:|
| HK full | 0.167 | 0.17 | -0.22 | YES |
| HK modern 2010+ | 0.309 | 0.31 | -0.35 | YES |

**Harness validated: PASS.** The CA verdicts below run on a harness proven to reproduce BOTH the shared base harness and the live HK fork — the intent of the acceptance gate (masterplan §4.1) is met; the harness is trustworthy. The masterplan's numeric pin is flagged stale for the program owner.

## CA NAMES · 12-1 · fwd21 (survivorship-biased, current constituents)

Span 2023-07-31..2026-05-29 · 35 monthly rebalances · ~219 names · beta 252d (shrink 0.66) · formation 252d (skip 21d) · forward 21d · market+sector residual.

IC scorecard (rank-IC per monthly cross-section; **bold = pre-registered decision trial**, others diagnostic-only):

| signal | mean IC | IC-IR ann | t_HAC | p_HAC | q_FDR | hit | n |
|---|--:|--:|--:|--:|--:|--:|--:|
| ir_res|SN | 0.0377 | 1.218 | 3.013 | 0.0026 | — | 0.657 | 35 |
| mom_res|SN | 0.0358 | 1.181 | 3.311 | 0.0009 | — | 0.686 | 35 |
| ir_res | 0.0383 | 1.145 | 3.326 | 0.0009 | — | 0.629 | 35 |
| **mom_res** | 0.0369 | 1.113 | 3.951 | 0.0001 | 0.0002 | 0.657 | 35 |
| rev_st | 0.05 | 0.968 | 2.601 | 0.0093 | — | 0.543 | 35 |
| mom_tot|SN | 0.0289 | 0.889 | 3.23 | 0.0012 | — | 0.6 | 35 |
| rev_st|SN | 0.021 | 0.671 | 1.137 | 0.2555 | — | 0.457 | 35 |
| **mom_tot** | 0.0254 | 0.422 | 0.744 | 0.4568 | 0.4568 | 0.571 | 35 |
| acc_res | -0.0062 | -0.253 | -0.521 | 0.6026 | — | 0.4 | 35 |
| acc_res|SN | -0.008 | -0.339 | -0.787 | 0.431 | — | 0.4 | 35 |

Top-vs-bottom dollar-neutral LS backtest (next-bar fill, net of 5bps one-way, DSR at PROGRAM n_trials=30):

| signal | net Sharpe | cum % | DSR | verdict | bootstrap Sharpe CI | P(SR>0) |
|---|--:|--:|--:|---|---|--:|
| mom_tot | 0.875 | 86.4 | 0.2649 | FAILS multiple-testing haircut (DSR<0.90) | [0.0, 0.9, 1.8] | 0.976 |
| mom_res | 1.062 | 69.4 | 0.3746 | FAILS multiple-testing haircut (DSR<0.90) | [0.13, 1.06, 1.99] | 0.987 |

Split-half sign-stability (first vs second time-half):

| signal | IC h1 | IC h2 | IC stable | LS Sharpe h1 | LS Sharpe h2 | LS stable |
|---|--:|--:|:--:|--:|--:|:--:|
| mom_tot | -0.0084 | 0.0573 | NO | 0.912 | 1.033 | YES |
| mom_res | 0.0372 | 0.0365 | YES | 1.46 | 0.927 | YES |

**Pre-registered gate verdicts (this panel):**
- `mom_tot` → **ACCRUE** (HAC t 0.744 < 2.0; fails BH-FDR(family); DSR 0.2649 < 0.90 (n_trials=30); split-half unstable (ic -0.0084/0.0573, sh 0.912/1.033))
- `mom_res` → **ACCRUE** (DSR 0.3746 < 0.90 (n_trials=30))

## CA SECTOR-ETFs · 12-1 · fwd21 (survivorship-clean; market-only residual)

Per-ETF inception (survivorship-clean sleeves): XEG 2001-03-23, XFN 2001-03-29, XGD 2001-03-29, XMA 2005-12-28, XIT 2001-03-23, XUT 2012-01-24, XRE 2002-10-22, XST 2012-01-24, XCG 2006-11-10, XCD 2013-04-08, ZEB 2010-04-20, XBM 2012-01-24.

Span 2003-04-30..2026-05-29 · 278 monthly rebalances · ~12 names · beta 252d (shrink 0.66) · formation 252d (skip 21d) · forward 21d · MARKET-ONLY residual.

IC scorecard (rank-IC per monthly cross-section; **bold = pre-registered decision trial**, others diagnostic-only):

| signal | mean IC | IC-IR ann | t_HAC | p_HAC | q_FDR | hit | n |
|---|--:|--:|--:|--:|--:|--:|--:|
| ir_res | 0.0559 | 0.458 | 1.922 | 0.0546 | — | 0.56 | 159 |
| rev_st | 0.0496 | 0.401 | 1.8 | 0.0718 | — | 0.558 | 172 |
| **mom_res** | 0.0454 | 0.366 | 1.402 | 0.161 | 0.2351 | 0.553 | 159 |
| **mom_tot** | 0.0392 | 0.315 | 1.187 | 0.2351 | 0.2351 | 0.578 | 166 |
| acc_res | -0.0484 | -0.398 | -1.357 | 0.1747 | — | 0.497 | 155 |

Top-vs-bottom dollar-neutral LS backtest (next-bar fill, net of 5bps one-way, DSR at PROGRAM n_trials=30):

| signal | net Sharpe | cum % | DSR | verdict | bootstrap Sharpe CI | P(SR>0) |
|---|--:|--:|--:|---|---|--:|
| mom_tot | 0.07 | -22.9 | 0.0412 | FAILS multiple-testing haircut (DSR<0.90) | [-0.3, 0.07, 0.46] | 0.648 |
| mom_res | 0.136 | 10.9 | 0.078 | FAILS multiple-testing haircut (DSR<0.90) | [-0.22, 0.14, 0.51] | 0.769 |

Split-half sign-stability (first vs second time-half):

| signal | IC h1 | IC h2 | IC stable | LS Sharpe h1 | LS Sharpe h2 | LS stable |
|---|--:|--:|:--:|--:|--:|:--:|
| mom_tot | 0.092 | 0.0289 | YES | -0.096 | 0.262 | NO |
| mom_res | 0.1023 | 0.0372 | YES | 0.066 | 0.246 | YES |

**Pre-registered gate verdicts (this panel):**
- `mom_tot` → **ACCRUE** (HAC t 1.187 < 2.0; fails BH-FDR(family); DSR 0.0412 < 0.90 (n_trials=30); split-half unstable (ic 0.092/0.0289, sh -0.096/0.262))
- `mom_res` → **ACCRUE** (HAC t 1.402 < 2.0; fails BH-FDR(family); DSR 0.078 < 0.90 (n_trials=30))

---

## Effective-N honesty
- **Names leg:** ~48–54 monthly rebalances over 2021-06→2026-06, but 21d-forward windows overlap ~1:1 within a month, so INDEPENDENT monthly cross-sections ≈ 24, and independent episodes (distinct momentum regimes in 5y) are far fewer (~2–4: the 2022 drawdown, the 2023–24 recovery, 2025–26). This is structurally too thin for DSR≥0.90 — a names-leg GO would need an implausibly clean signal; the honest ceiling here is **ACCRUE**.
- **Sector-ETF leg:** ~285 monthly rebalances over 2002→2026 (~24 years). XBM begins 2012-01-24, so the copper/base-metals sleeve contributes ~14y, not 24y. Independent sector-rotation cycles over 24y are ~8–12; the effective-N is materially below the raw rebalance count. This is the strongest-powered leg but still episode-limited.

## Survivorship bound (not a stamp)
- **Names leg:** `data/canada_search/closes.parquet` is CURRENT-CONSTITUENT (219 names on today's TSX composite). Delisted losers are absent → momentum long-short is biased UP. Therefore a names-leg **GO is an optimistic upper bound**; a names-leg **NO-GO is conservative** (survivorship only helps momentum, so a fail on the survivor panel is a strong fail). No dead-name store exists ex-US to compute the worst-case lower bound.
- **Sector-ETF leg:** survivorship-CLEAN — the ETFs are the sleeves themselves, continuously listed; no constituent-survivorship in the sleeve return.

## What this does NOT show
This battery tests ONLY cross-sectional 12-1 momentum (total and beta-stripped residual) as a standout-board rank basis. A NO-GO/ACCRUE here does NOT mean Canada has no tradable edge — the masterplan's vindicated C1 commodity→sector transmission, C-BANK earnings clustering, and the ripe-list contract are separate mechanisms tested elsewhere. It does NOT test name-level catch-up (dropped; sign against), time-series momentum, alternative formation/holding windows, or any conditioner. It does NOT establish survivorship-neutral names-leg performance (bounded, not neutralized). Diagnostic rows (ir_res, rev_st, acc_res, |SN) are shown for context and are explicitly NOT pre-registered decision trials.
