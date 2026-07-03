# C1 — Commodity→Sector Transmission — Phase-0 Report

**Battery:** C1 (HK/Canada masterplan §4.1, W2). **Branch:** `hkca-w2-c1`.
**Pre-registration:** `research/C1_COMMODITY_SECTOR_PREREG.md` (committed BEFORE any run — audit
trail `4c583f7`). **Harness:** `scripts/c1_commodity_sector_phase0.py`. **NO wiring** (reports only).

---

## VERDICT

**Zero GO. One ACCRUE, three NO-GO — exactly the pre-registered honest-prior outcome.**

- **oil → XEG.TO — ACCRUE.** Positive and statistically clean on episode-honest stats (HAC
  t = **+2.75** at 4w, mean excess **+1.87%**, hit 66%, passes BH-FDR at 0.10, split-half
  **same-sign positive**, bootstrap P(mean>0) = 0.99) — but **DSR = 0.54 < 0.90** at program
  n_trials=30, so it fails the only door to a GO. A real, direction-confirmed, but multiplicity-
  underpowered signal → ACCRUE, register, come back.
- **gold → XGD.TO — NO-GO.** Flat at every horizon (HAC t = **−0.04** at 4w, mean **−0.04%**),
  split-half **sign-flips**. This does **NOT** reproduce the red-team's raw XGD 4w t = +2.42 — and
  the divergence is **not** the overlap correction (overlapping-window replication on my regime
  definition is also t = −0.04). It is the **regime definition**: a pre-registered slope_z +
  hysteresis + min-duration episode construction produces bull entries where gold miners show no
  forward excess. Gold transmission is fragile to the exact turn definition.
- **copper → XBM.TO — NO-GO.** Flat (HAC t = −0.44, mean −0.65%), n=20 non-overlapping episodes,
  low-n (XBM 2012→). Secondary **copper → XMA.TO** (2005→) also NO-GO (t = −0.23, split-flip).

The C1 sector-tier is **weaker than the raw replication ceiling** once episode-honesty is enforced:
only oil survives with a real positive edge, and even oil does not clear the DSR bar. This is the
masterplan's planned "GO-or-ACCRUE, borderline by construction" prior landing on the ACCRUE side —
a respectable, pre-committed outcome, not a failure to torture into a GO.

---

## Pre-registered gates vs results (primary horizon = 4w)

GATED family (3 trials, BH-FDR within family, DSR at n_trials=30):

| Trial | n(non-ovlp ep) | mean excess | HAC t | BH-FDR reject? | DSR (n=30) | split-half same-sign | Verdict |
|---|---|---|---|---|---|---|---|
| **T1 oil→XEG** | 32 | **+1.87%** | **+2.75** | **YES** (q=0.009) | 0.541 | YES (+1.46% / +2.29%) | **ACCRUE** |
| T2 gold→XGD | 32 | −0.04% | −0.04 | no (q=0.67) | 0.018 | NO (−0.30% / +0.18%) | NO-GO |
| T3 copper→XBM | 20 | −0.65% | −0.44 | no (q=0.67) | 0.007 | (2 vs 18; n/a) | NO-GO |
| *T3b copper→XMA (secondary)* | 26 | −0.20% | −0.23 | *(not in gated family)* | 0.013 | NO | NO-GO |

Gate reference (pre-reg §5): **GO** requires HAC t ≥ +2.0 AND BH-FDR reject AND **DSR ≥ 0.90** AND
split-half same-sign AND n ≥ 8. Oil clears every gate **except DSR** (0.54) → ACCRUE by the
pre-registered rule (positive mean + HAC t ≥ 1.0 / DSR ≥ 0.50). No trial reached DSR ≥ 0.90.

### Horizon curve (robustness within the same test, mean / HAC t / DSR)
| Trial | 2w | 4w (primary) | 6w | 8w |
|---|---|---|---|---|
| oil→XEG | −0.2% / −0.32 / 0.01 | **+1.9% / +2.75 / 0.54** | +2.2% / +2.70 / 0.44 | +3.2% / +3.44 / 0.58 |
| gold→XGD | +0.2% / +0.29 | −0.0% / −0.04 | +1.2% / +0.71 | +0.7% / +0.33 |
| copper→XBM | +0.1% / +0.07 | −0.6% / −0.44 | +0.1% / +0.08 | −0.1% / −0.08 |

Oil transmission is **absent at 2w** and **builds over 4–8w** (t rises to +3.4 by 8w) — a coherent
"sector re-rates over the following month-plus," not a 2-week pop. Gold and copper are flat at all
horizons. Even oil's best horizon (8w, DSR 0.58) does not clear 0.90.

---

## Split-half sign-stability (pre-registered split at 2013-01-01)

- **oil→XEG:** pre-2013 mean **+1.46%** (n=16), post-2013 **+2.29%** (n=16) — **same-sign positive,
  stable.** This is the sign-stability a GO requires; oil passes it. (DSR, not sign-stability, is
  what holds oil back.)
- **gold→XGD:** pre **−0.30%** / post **+0.18%** — **sign-flip** → NO-GO.
- **copper→XBM:** only 2 pre-2013 episodes (XBM inception 2012) — split-half is **informational
  only**, as pre-registered; the trial is NO-GO on its flat full-sample mean regardless.

---

## Effective-N honesty

Effective-N is the **non-overlapping independent-episode count**, not row count, not raw flip count.
Three counts reported per pre-reg §6:

| Trial | raw slope flips (into bull) | confirmed episodes (≥20d) | **non-overlapping 4w episodes** | daily-stream t_eff / raw |
|---|---|---|---|---|
| oil→XEG | 35 | 32 | **32** | 640 / 640 (ratio 1.00) |
| gold→XGD | 36 | 32 | **32** | 640 / 640 |
| copper→XBM | 29 | 29 | **20** | 400 / 400 |

**Surprise, reported not hidden (§6.1):** the pre-reg expected ~8–16 episodes per full-history
commodity; the realized count is **~32** — near the critic's *upper* "43–50 debounced turns" basis,
not the "~6–12 independent cycles" lower bound. Cause: the ±0.5 hysteresis re-arms a bull entry
after any dip below −0.5, so an extended uptrend with pullbacks yields several bull episodes. This
is the **pre-registered construction run as written** — I did **not** re-tune it post-hoc (that
would be p-hacking). At n≈32 the tests are better-powered than the pessimistic prior, yet oil still
fails DSR — the multiplicity haircut at n_trials=30, not sample size, is the binding constraint.

The block-bootstrap `t_eff` on the daily in-window excess stream shows ratio ≈ 1.00 (t_eff = raw):
the **non-overlap construction already removed the window-overlap autocorrelation** the critic
warned about, so there is no further effective-N collapse to apply. The critic's inflation concern
is handled by construction, not by a post-hoc bootstrap deflation.

---

## Exploratory, NON-GATED: the negative-flip (de-rate) side

Reported per pre-reg §1 (drawdown-side use if the long side fails); NOT FDR-corrected, NOT DSR-gated.

| Negative-flip trial (4w) | n | mean excess | HAC t | hit |
|---|---|---|---|---|
| oil→XEG after BEAR flip | 32 | **−1.16%** | −1.78 | 38% |
| gold→XGD after BEAR flip | 32 | +1.85% | +1.72 | 56% |
| copper→XBM after BEAR flip | 20 | +0.90% | +0.72 | 60% |

Oil is **directionally symmetric**: XEG *under*performs after a bearish oil flip (t = −1.78),
mirroring its outperformance after a bullish flip — the one commodity→sector pair with a coherent
two-sided story. Gold miners *out*perform after gold bear flips (t = +1.72, opposite of a de-rate),
consistent with the gold long-side being noise/contrarian rather than a transmission channel. These
are exploratory only and change no verdict.

---

## Survivorship stamp

**Index/ETF-level series — no name-panel survivorship exposure.** Commodities are continuous
adjusted futures; sector legs are ETFs (XEG/XGD/XBM/XMA) and the benchmark is _GSPTSE. There is no
cross-sectional name selection, so no current-constituent survivorship bias (the masterplan drops
the C1 name tier entirely). The only survivorship channel is ETF discontinuation — none of the four
ETFs delisted over the window (all live to 2026-06-30). **Survivorship bound: none material at the
ETF level.** (Contrast the HK/CA name panels, which carry current-constituent survivorship and
require a delisted-name imputation bound.)

Suspension/halt rule (pre-reg §2.3) enforced: windows running past the last available bar are
DROPPED (no partial/ffill'd window); leg gaps use the present-bar intersection (no ffill through a
gap). Canadian ETFs did not halt for weeks over the window, but the rule is in the code.

---

## What this does NOT show

- **Not a name-level edge.** The C1 name tier (high-beta resource names catching up to their metal)
  is dropped by the masterplan and refuted by the red-team (GDX–XGD t+1 residual −0.06; miners
  anticipate, not lag). This report tests only the **sector-ETF** tier.
- **Not a tradeable strategy.** Episode returns are **gross buy-and-hold excess** — no transaction
  costs, slippage, capacity, or borrow. Oil's +1.9%/4w is a gross signal, not a net P&L.
- **Not causal.** Commodity regime flips co-move with macro states (USD, rates, risk appetite) that
  independently move TSX sectors; this is an association net of the broad-market leg, not an
  identified transmission mechanism.
- **Not out-of-sample.** Split-half at 2013 tests in-sample sign-stability, not walk-forward OOS.
- **Regime-definition-dependent.** The gold null and (by symmetry) the oil ACCRUE are conditional on
  the pre-registered slope_z + ±0.5 hysteresis + 20d min-duration definition. A different turn
  definition can move the gold result — which is precisely why the definition was frozen before the
  run. Any alternative must be pre-registered before running, not chosen to rescue a verdict.
- **DSR n_trials.** Uses the program-level n_trials = 30 (masterplan §6, counting configs across
  both markets), not just this family's 3–4 — the honest, conservative multiplicity count.

---

## Registry

Experiment `hkca-c1-commodity-sector` registered in `data/experiments/registry_seed.json`
(kind `phase0_backtest`, come_back_on 2027-01-15 — re-run when XBM/base-metals copper history
lengthens; oil→XEG ACCRUE revisited if episode count grows enough to move DSR). No forward ledger
(in-tree 25y backtest, decision-grade now). **Nothing wired to any live engine or board.**
