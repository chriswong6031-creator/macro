# Pre-registration — Forward Shadow Book verdict on `stock_score`

**Author:** Head of Research · **Registered:** 2026-06-21 · **Status:** FROZEN before maturation.

This document fixes — in advance and immutably — what would count as the live
`stock_score` carrying realized cross-sectional alpha, and what we will DO at each
outcome. It exists because the institutional failure mode is not a bad score; it is
moving the goalposts once the score has a number. The keystone forward shadow book
(`engine/shadow_book.py`, PR #381 / `dd41da9c8`, on `origin/main`) is empty by
design until horizons elapse; this is registered while it is empty so the bar
cannot be tuned to whatever the data later shows.

> **One-line prior:** given the committed factor scorecard (composite IC −0.0072;
> only `payout` survives BH-FDR; everything graded on the *optimistic* survivor
> bound), the strong prior is that the forward book shows `stock_score`
> cross-sectional forward IC ≈ 0. **Confirming that is the institutional win, not a
> loss** — the system would, for the first time, *know* its traded score carries no
> realized cross-sectional alpha, and act on it.

---

## 1. What is being graded (frozen)

- **Object:** the live, build-time-frozen `stock_score` percentile rank over the
  traded US equity universe, as snapshotted by `shadow_book.snapshot()` at each
  nightly build (no backfill, no restatement).
- **Metric:** forward cross-sectional **rank-IC** of the frozen score vs realized
  forward total return, per horizon **h ∈ {21, 63, 126} trading days**, matured
  only after the horizon has *fully elapsed* (the leak guard, unit-tested in
  `tests/test_shadow_book.py`).
- **Aggregation:** IC mean, **IC-IR (annualized)**, HAC/Newey–West t-stat
  (`engine/validation.newey_west_tstat`), and **Clark–West** vs an expanding-mean
  benchmark (`engine/validation.clark_west`). All already implemented.
- **Effective sample (frozen definition):** N = number of distinct **entry-date
  clusters** that have matured at horizon h — **not** the raw row count. A nightly
  rebuild that re-snapshots the same names is one cluster, not hundreds. This is the
  honest N that goes into every CI and into the DSR deflation below.

## 2. Decision rules (frozen — one per outcome)

Evaluated **per horizon**, only once the minimum sample (§3) is reached.

| Outcome at horizon h | Pre-registered verdict | Action (committed now) |
|---|---|---|
| **PASS** — IC-IR_ann > 0 **and** HAC t > 2.0 **and** Clark–West p < 0.05 **and** survives DSR (§4) | The score carries realized cross-sectional alpha at h | Keep sizing on it at h; publish the audit; promote h as a graded horizon |
| **NULL** — \|IC-IR_ann\| small and HAC t ≤ 2.0 (fails to reject zero) | No realized cross-sectional alpha at h (the prior) | **Stop sizing positions on the cross-sectional `stock_score` at h.** Demote it to context/display only. Publish the null. |
| **NEGATIVE** — IC-IR_ann < 0 **and** HAC t < −2.0 | The score is anti-predictive at h | Stop sizing immediately; investigate sign/leakage; publish |

"Stop sizing" means the portfolio/Mastermind layer must not take cross-sectional
position weight from `stock_score` at that horizon; the score may still render as
context with the verdict stamped. No outcome permits *raising* exposure beyond
current sizing — this is a subtract-only gate, consistent with the rest of the
stack.

## 3. Minimum sample & latency (frozen)

- **No verdict before** N ≥ **6 matured entry-date clusters** at the horizon AND
  ≥ **2 calendar quarters** of matured history (whichever is later). Below this the
  audit reads **"building"**, never PASS/NULL/NEGATIVE — mirroring the
  `MIN_DATES` discipline already used in the cross-sectional scorer.
- The 126d horizon will mature last (~6+ months); its verdict may lag the 21/63d
  verdicts by quarters. That is expected and is not grounds to widen the bar.

## 4. Multiple-testing & anti-gaming guardrails (frozen)

1. **DSR deflation.** Any PASS headline is deflated by the **program-wide trial
   count** from the canonical `data/trial_ledger.jsonl` via `deflated_sharpe`. We
   are grading three horizons here; that is itself ≥3 trials and is logged.
2. **The bar above does not move.** Thresholds, horizons, metric, and the
   effective-N definition are fixed by this document's registration date. A change
   requires a new dated pre-registration that supersedes this one in git history —
   never an in-place edit after seeing results.
3. **Grade the full traded universe**, not a clean subset; stamp the
   survivorship/`dead_name_coverage` caveat on the artifact (the score trades a
   survivor-biased price universe → the forward IC is itself an *optimistic* bound;
   see [Phase 1B dead-name fundamentals](INSTITUTIONAL_ROADMAP.md)).
4. **One-sided humility.** Because the bar is pre-registered and the prior is null,
   a NULL result is reported with equal prominence to a PASS. The win condition of
   this program is a *trustworthy* verdict, not a positive one.

## 5. Why this is registered now

The shadow book has **0 matured rows today**. Registering the success bar while the
evidence does not yet exist is the only way the eventual verdict is credible. When
`site/shadow/audit.json` first crosses the §3 sample floor, the §2 table is applied
mechanically — no discretion, no re-derivation. This pre-registration is the
contract.

**Linked work:** keystone build = `engine/shadow_book.py` + `scripts/mature_shadow_book.py`
(PR #381). De-bias of the graded universe = Phase 1B dead-name fundamentals
(`collectors/edgar_deadnames.py`, this PR) — as dead-name price coverage arrives,
the "optimistic bound" caveat tightens and this verdict is re-run on the de-biased
universe under the same frozen bar.
