---
key: PRICE-LADDER-CONTROL-DERIVES-ITS-ASSUMPTION
question: >
  test_non_payer_and_no_exdiv_names_agree_across_bases reds main whenever one of
  its four hardcoded control names acquires an ex-date after CFG_DATE. Re-pin the
  ticker list to names that currently have no post-rebuild ex-date, or express the
  control as the mechanism it is actually claiming?
answer: >
  Express the mechanism. The control now asserts that each name's two bases differ
  only by ONE constant factor over a contiguous prefix that converges to exact
  agreement — the signature of back-adjustment — instead of asserting that four
  chosen names happen to agree on one date.
rationale: >
  The control exists to rule out "the two stores are simply different data" as an
  alternative explanation for the CFG gap. Exact agreement was only ever a PROXY
  for that, and the proxy expires: a name is a valid control until its next
  dividend, so the list decays with the calendar and reds the fleet on a data
  event nobody caused. The single-factor-converging signature IS the claim, is
  strictly stronger (different data cannot fake a constant ratio that converges
  once and stays converged), and needs no maintenance. Measured on the four real
  names: JPM 1.004505 over 307 points, KO 1.006456 over 293, ALB 1.002553 over
  290, CEG 1.001537 over 335 — identical structure; the only difference is that
  CEG's last ex-date (2026-07-17) falls AFTER CFG_DATE and the other three fall
  before it. Nothing about CEG became different data.
alternatives:
  - option: Re-pin the ticker list to names with no current post-rebuild ex-date.
    why_not: >
      Restores green and re-arms the same trap for the next dividend; it also
      silently shrinks the control's evidence each time a name is dropped.
  - option: Loosen the 1e-3 tolerance.
    why_not: >
      The sibling receipt says in its own message "if the cache was rebuilt this
      receipt must be re-measured, never loosened", and a tolerance wide enough to
      swallow a 0.15% re-base is also wide enough to swallow a real ladder
      regression.
  - option: Drop CEG from the control list.
    why_not: Same defect as re-pinning, minus the evidence.
evidence: >
  Local reproduction on origin/main: "CEG disagrees across bases at 2026-06-22 —
  the control assumption moved; assert 275.5299987792969 == 275.1070861816406 ±
  0.001" (0.153%, a distribution factor). Same three steps red on main's own run
  32220671521 at 7db745f4 with no PR diff involved, and on two PRs with disjoint
  diffs (#5922, #5737). After the change the whole CI step is 106 passed, 1
  skipped. Precedent: DSC:HK-DEEP-PANEL-SPLICES-ADJUSTMENT-VINTAGES and
  DEC:HK-G1-FIXTURE-BANDS-THE-REFRESH-SUFFIX healed the identical class on the HK
  board fixture in #5896 with the same mechanism-derived shape.
reversibility: easy
affects:
  - research/prophet_us_audit/test_price_ladder.py
  - .github/ci/legacy-jobs.yml
confidence: high
scope:
  - macro
  - research/prophet_us_audit/test_price_ladder.py
decided_at: 2026-08-19
decided_by: claude/price-ladder-control-derives-its-names
---

## Why a skipping test could not carry this

The module's own docstring says *"A skipping test proves nothing"*, and the control is store-dependent — it cannot run on a pack with no `data/` tree. So `adjustment_diagnosis` is pinned separately by `TestAdjustmentDiagnosis`, eight synthetic cases that never skip: identical bases, a converging single factor at CEG's real ratio, a wandering ratio, a split-sized ratio, a converge-then-diverge splice, an empty date intersection, a non-positive adjusted close, and a NaN that must not manufacture a disagreement.

## One branch was dead as first written

The convergence check was originally "does anything AFTER the last disagreement still disagree" — which can never fire, because the last disagreement is by definition the last one. The property that actually distinguishes an adjustment from a splice is **contiguity**: back-adjustment scales a contiguous prefix, so a date that agrees *in the middle* of the disagreeing range is the tell. The check now looks for that, and the synthetic case exercises it.
