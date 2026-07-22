# C1-R2 — oil → XEG.TO confirmatory pre-registration

**Status: PRE-REGISTERED — committed BEFORE any R2 statistic is computed.**
Author: strategy-redesign program (commodities lane). Round 2 of the C1 commodity-sector transmission study.

## 0. Why this exists (and what it corrects)

C1-R1 (`research/C1_COMMODITY_SECTOR_PREREG.md` → `reports/c1-commodity-sector-phase0.md`) tested oil/gold/copper → their Canadian sector ETFs. **oil → XEG.TO landed ACCRUE**, and it is the only real edge in the family:

- n = 32 non-overlapping 4-week episodes, mean excess **+1.87%**, HAC **t = +2.75**, BH-FDR **reject (q = 0.009)**, bootstrap **P(mean > 0) = 0.99**.
- Split-half **sign-stable**: pre-2013 +1.46% (n=16), post-2013 +2.29% (n=16) — the sign-stability a GO requires.
- It cleared **every pre-registered GO gate except DSR** (0.541 < 0.90).

The R1 report's own §6.1 ("surprise, reported not hidden") is the key finding that drives R2: the prereg expected ~8–16 episodes; it got n≈32, so the test was **better-powered than the prior — yet oil still failed DSR**. The report states plainly: *"the multiplicity haircut at n_trials = 30, not sample size, is the binding constraint."* (`reports/c1-commodity-sector-phase0.md:89-90`).

**Implication (corrects the redesign masterplan draft):** the masterplan's proposed fix — "run oil→XEG to conclusion on a proper dated-futures vendor / gather more episodes" — is **misdirected**. More episodes do not shrink the n_trials=30 multiplicity haircut. The honest R2 is not "more data on the same exploratory test"; it is a **single confirmatory pre-registration (n_trials = 1)** whose multiplicity is 1 by construction, evaluated on **out-of-sample episodes only**. This is the standard two-stage design: R1 explored a 30-config family and generated the hypothesis; R2 freezes the single winner and confirms it on data R1 never saw. The multiplicity of R1's search is "paid for" by requiring a clean OOS confirmation — not by re-scoring the same episodes at a friendlier n_trials.

## 1. Hypothesis (single, frozen)

**H_C1R2 (one-sided):** A confirmed oil bull-flip episode precedes a **positive 4-week excess return in XEG.TO** (Canadian energy) over its benchmark, out-of-sample, with the same positive sign and comparable magnitude as R1.

This is the **only** hypothesis in the R2 family. n_trials = 1. No sibling sectors, no horizon sweep, no alternate episode definitions are tested under this registration (those would re-inflate multiplicity and void the confirmatory logic).

## 2. Frozen construction (identical to R1 T1 — no re-optimization)

- **Oil episode:** raw front-month WTI slope flips into bull, **confirmed ≥ 20 trading days** (R1 definition, verbatim). Non-overlapping 4-week outcome windows.
- **Outcome:** XEG.TO total-return excess over the R1 benchmark, primary horizon **4 weeks** (frozen; the 8w curve is NOT a fallback under this registration).
- **Estimator:** episode-honest stats — HAC (Newey-West) t on non-overlapping episodes, block bootstrap P(mean>0), split-half sign check. Exactly R1's apparatus (`reports/c1-commodity-sector-phase0.md:34-47`).
- **No parameter is re-fit.** Any change to the episode definition, horizon, benchmark, or universe invalidates this prereg and requires a fresh one.

## 3. Data & sample (out-of-sample only)

- **Confirmatory set = oil bull-flip episodes whose 4-week window CLOSES after the frozen cutoff `2026-07-22`** (R1's data end). Episodes accrue forward through the nightly lane.
- **Known constraint (stated, not hidden):** oil bull-flip episodes are rare (~1–2 non-overlapping/yr). A powered confirmatory set (n_oos ≥ 8) will take **years** to accrue. This is expected; R2 is a slow forward confirmation, not a fast re-test. There is no shortcut that preserves the confirmatory logic.
- Data is NOT blocked (XEG.TO + WTI both in-engine); the limiting resource is calendar time / episode arrival, not vendor coverage.

## 4. Pre-registered gates (confirmatory, n_trials = 1)

Evaluated only when **n_oos ≥ 8** non-overlapping episodes have accrued:

- **GO (promote to display-tier CONFIRMER):** OOS mean > 0 AND HAC t ≥ **+2.0** AND same sign as R1 (positive) AND **DSR ≥ 0.90 at n_trials = 1** AND split-half sign-stable within the OOS set.
- **ACCRUE (keep waiting):** OOS mean > 0 AND HAC t ≥ 1.0 but DSR < 0.90 or n_oos < 8.
- **KILL (close the channel):** OOS mean ≤ 0 OR sign flip vs R1 OR HAC t < 1.0. This RETIRES the oil→XEG construction (registers a row in `DO_NOT_REBUILD.md §2`), it does not loop back to ACCRUE forever.

At n_trials = 1 the DSR haircut collapses to the single-hypothesis PSR; with R1's observed effect (Sharpe-equivalent), clearing 0.90 OOS is plausible **iff the effect persists** — which is exactly what the OOS test decides. A circular-shift timing placebo (2000 draws) on the OOS episodes is required alongside DSR.

## 5. Interim status until GO — DISPLAY-TIER CONTEXT CHIP ONLY

Per R1's own recommendation (*"a live context chip, not a scored ranker"*, `reports/c1-commodity-sector-phase0.md`), and per the constitution (display-tier ships freely; a null never blocks display):

- oil→XEG may render as a **display-tier context chip** on the commodities / Canadian-energy surfaces — plain-word framing (e.g. "oil turned up → historical tailwind for Canadian energy; not a gauntleted score"), with the R1 numbers as a Tier-2 receipt.
- It may **NOT** be a scored ranker, a gate, or a size input until GO. **No LLM originates or escalates this key** — the chip reflects the R1-calibrated relationship at display tier; promotion to CONFIRMER is an operator/nightly action gated on §4.

## 6. Anti-overfitting / integrity guards

- Episode definition, horizon, benchmark FROZEN from R1 — no re-optimization (re-fitting here would be the p-hack the R1 report explicitly refused, §6.1).
- Era-split (pre/post-2013) reported on the OOS set.
- Program n_trials for THIS registration = 1 by construction; do not fold sibling-sector or horizon variants into R2 (they belong to a separate exploratory family, already NO-GO in R1).
- Forward ledger advanced by the nightly lane only.

## 7. Verdict log (append-only)

_(empty until n_oos ≥ 8; each evaluation appends {as_of, n_oos, mean, HAC_t, DSR@1, placebo_p, verdict})._
