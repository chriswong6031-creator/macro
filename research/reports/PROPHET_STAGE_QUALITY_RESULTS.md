# Prophet × Stage quality re-grade — backtest results (PSQ)

Spec: `research/PROPHET_STAGE_QUALITY_PREREG.md` · generated 2026-07-20T23:57:46.540890+00:00

## §0 SAME-SAMPLE DISCLOSURE (read first)

> **SAME-SAMPLE CONFIRMATORY RE-ANALYSIS.** The PSF run (predecessor test) already
> observed the return right-shift that PSQ tests (median fwd_ret_126 A→C 1.8%→4.7%).
> PSQ commits the bootstrap CI machinery and pass lines in the pre-registration
> (research/PROPHET_STAGE_QUALITY_PREREG.md) BEFORE re-running, so a CI straddling
> zero is filed as FAIL. The promotion consequence is therefore **provisional** and
> the binding out-of-sample confirmation is the live-Prophet forward shadow (#3157).
> The point estimates below were known before registration; only the CI machinery
> and pass lines were not.

> **PROXY DISCLOSURE (PSF §0 applies verbatim):** PROXY (PSF §0): Prophet has NO backtestable history (5 live entries post-2026-07-10). This is a FUSION-MECHANISM test on the repo's backing-artifact-backed T1-T4 confluence cascade as a PIT-replayable Prophet-family timing entry — NOT a Prophet replay. A positive result is evidence the mechanism helps Prophet's own entries, to be confirmed forward on live Prophet from go-live (~Dec 2026). Results are display-tier until operator-ratified promotion.

## Universe

- Union universe (baskets/ohlcv ∪ data/stocks, minus SPY bench): **2811** names; with usable prices: **2811**.
- Late-IPO names EXCLUDED (< 45 completed weeks at entry) and COUNTED: **18** (§7).
- Benchmark: SPY · entry window: 2022-01-01 … 2026-07-17.
- Full universe (no sampling).
- Total fresh fires (T1/T2, all names): **52078**. EC gate (arm C): earnings_call_sent ≥ 24.

### §0 SURVIVORSHIP DISCLOSURE

- Universe is **survivor-LEAN, not full PIT**. Live globs: **2520** names; delisted dead-name tickers UNIONED IN and COUNTED: **+291** (FIX-2).
- Residual gap: **336** S&P-1500 PIT members that traded 2022-01-01–2026-07-17 have NO price source anywhere and remain ABSENT; of 1889 PIT members that traded in-window.
- **Consequence:** survivor-LEAN, not full PIT: live globs UNION delisted dead-name tickers (+291 counted); 336 S&P-1500 PIT members that traded 2022-26 have NO price source anywhere and remain absent. Falsifier verdicts are DELTA-based (A→B→C); survivorship inflates all arms' ABSOLUTE win-rates ~symmetrically, so the null on the delta is robust to the residual lean, while absolute win-rates are upward-biased.

## Per-arm summary — matured fires, clean15_126

| Arm | n_matured | n_months | med fwd_ret_126 | med fwd_mfe_126 | med fwd_mdd_126 | med EA (mfe+mdd) | STOPPED rate | win-rate |
|---|---|---|---|---|---|---|---|---|
| A | 45294 | 49 | 2.29% | 18.48% | -14.61% | 3.87% | 66.81% | 30.98% |
| B | 15199 | 49 | 3.30% | 17.85% | -13.42% | 4.42% | 66.37% | 31.13% |
| B_fresh | 4488 | 49 | 3.07% | 17.75% | -13.09% | 4.66% | 65.75% | 31.55% |
| C | 4678 | 49 | 5.08% | 19.78% | -13.36% | 6.41% | 64.84% | 32.62% |

## PSQ bootstrap CIs — paired month-block, n_boot=10,000, seed=20260720

### PSQ-H1 (PRIMARY) — median fwd_ret_126, C−A

| Statistic | Value |
|---|---|
| n_matured C | 4678 |
| n_matured A | 45294 |
| n_months (union) | 49 |
| point median A | 2.29% |
| point median C | 5.08% |
| point diff C−A | 2.79% |
| economic floor (preregistered) | +1.5pp (+0.015) |
| boot mean | 2.76% |
| boot SE | 0.63% |
| 2.5% CI | 1.57% |
| 97.5% CI | 4.02% |
| CI [2.5%, 97.5%] | [1.5672%, 4.0190%] |
| CI lower > 0? | True |
| no-verdict? | False |

### PSQ-H1 decompositions (B−A and C−B — PRINTED, NO VERDICTS)

| Comparison | point diff | 2.5% | 97.5% | n_months |
|---|---|---|---|---|
| B−A | 1.02% | -0.19% | 2.23% | 49 |
| C−B | 1.78% | 0.59% | 2.89% | 49 |

### PSQ-H1 de-overlapped robustness (one fire per name per 126-bar window — SUPPORTING)

- n_fires de-overlapped: 23485 (from 52078)
- point diff C−A: 3.19%
- bootstrap CI [2.5%, 97.5%]: [1.4194%, 5.0785%]
- n_months: 49

### PSQ-H2 (secondary) — median EA (fwd_mfe_126 + fwd_mdd_126), C−A

| Statistic | Value |
|---|---|
| n_fires C (non-null EA) | 4678 |
| n_fires A (non-null EA) | 45294 |
| n_months | 49 |
| point median EA, A | 4.70% |
| point median EA, C | 7.42% |
| point diff C−A | 2.72% |
| CI [2.5%, 97.5%] | [0.9801%, 4.5231%] |
| no-verdict? | False |

### PSQ-H3 (secondary) — stopped fraction, C−A (negative = C better)

| Statistic | Value |
|---|---|
| n_months | 49 |
| point stopped fraction, A | 66.81% |
| point stopped fraction, C | 64.84% |
| point diff C−A | -1.97% |
| CI [2.5%, 97.5%] | [-4.5052%, 0.3107%] |
| CI upper < 0? | False |
| no-verdict? | False |

## Regime leg — H1 point diff per regime (SUPPORTING, no verdict change alone)

| Regime | n_dates (A) | n_fires C | n_fires A | med ret C | med ret A | diff (C−A) |
|---|---|---|---|---|---|---|
| 2022_bear | 250 | 615 | 11570 | -5.60% | -4.04% | -1.56% |
| 2023_24_bull | 502 | 2490 | 22093 | 6.96% | 3.41% | 3.55% |
| 2025_26 | 250 | 1573 | 11631 | 6.92% | 6.14% | 0.78% |

## §5 Mechanical verdicts (pre-registered falsifiers)

> These lines are MECHANICAL outputs. Adjudication text is in the placeholder section below.

- **PSQ-H1 (PRIMARY — quality tilt; median fwd_ret_126 C−A): `PASS`**
  - CI lower bound: 1.57% (must be > 0 to PASS; econ floor: point diff must be >= +1.5pp)
  - Point diff C−A: 2.79% (ABOVE +1.5pp floor)

- **PSQ-H2 (secondary — EA; no promotion/kill power): `PASS`**
  - CI [2.5%, 97.5%]: [0.9801%, 4.5231%]

- **PSQ-H3 (secondary — stopped fraction; no promotion/kill power): `FAIL`** (CI upper >= 0 → FAIL)
  - CI [2.5%, 97.5%]: [-4.5052%, 0.3107%]

- **KILL predicate (DO_NOT_REBUILD trigger): `not triggered`**
  - Reason: negative in >= 2 regimes at n_dates >= 50: ['2022_bear']

## Per-fire dump (reproducibility artifact)

- Per-fire parquet committed at `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/agent-acd06d6c505aeadc4/data/research/psf_fires.parquet` (1.8 MB).

## PSF win-rate falsifiers (carried from predecessor test — context only)

- PSF-H1 (B−A win-rate): `FAIL` — bootstrap CI [-1.8836%, 2.1999%] (n_months=49)
- PSF-H2 (C−B win-rate): `FAIL` — bootstrap CI [-0.5927%, 3.6175%] (n_months=49)
- PSF KILL: `TRIGGERED`

## Adjudication (main loop)

PENDING
