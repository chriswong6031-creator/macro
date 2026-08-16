---
key: FUSION-FAMILY-NEAR-CONSTANCY-IS-A-REGISTRY-QUESTION
question: >
  F8 handed 99% of rows and F4 97% of rows an identical contribution on the first live
  fusion pool, so five ACTIVE families are not five independent ordering votes. Is that
  a defect in the as-of-night variance floor that should be re-tuned, a reason to drop
  F4/F8, or something else?
answer: >
  Something else, and the distinction is the ruling: FAMILY ADMISSIBILITY and EFFECTIVE
  CROSS-SECTIONAL DISCRIMINATION are two different properties, and the floor governs
  only the first. A family that clears both floors is admissible; whether it did any
  ordering work on a given night is a measurement about that night's coverage. The
  observed near-constancy is therefore a REGISTRY/MEASUREMENT question carried to w3,
  and is NOT evidence the floor is mis-set. The floor is not re-tuned, F4/F8 are not
  dropped, no fitted weight is introduced, and C1 is not altered to improve the
  observed ranking. w3 instruments the question descriptively — contribution
  dispersion, tie/near-tie fraction, and preferably leave-one-family-out rank
  displacement or an equivalent deterministic ordering-contribution measure. Those
  diagnostics are DESCRIPTIVE: in this wave they neither gate a family nor reweight
  C1, and a family may not be dropped on the strength of them.
rationale: >
  Re-tuning the floor against the ordering it just produced is fitting to an observed
  outcome, which is the exact failure the whole promotion gate exists to refuse — and
  it would be fitting via the least visible route available, since the floor looks like
  a data-quality parameter rather than a coefficient. The floor is FEATURE-ONLY law: it
  asks whether a member varies enough tonight to be capable of carrying information,
  not whether it happened to separate names in the order that resulted. A
  sparse-but-variable event flag passing while contributing one tied value to almost
  every row is the REGISTERED acceptance behaviour of that rule, not a violation of it.
  The near-constancy is also not a hidden finding that a re-tune would fix: it is
  published in the comparison's family-separation table on every run, so a reader can
  see that a listed family did almost no ordering work. Measured, printed, not acted on
  is the correct handling of a descriptive fact about one night's coverage.
  The substantive question underneath — is this persistent or pool-specific? — cannot
  be answered from the pool that raised it. F1 is the standing warning: it is ABSENT
  across the frozen 24-date frame (tier_cascade 0.25) and ACTIVE live (~1.00), same
  code and same thresholds, different frame. A family's discrimination is a property of
  coverage, so one board is one observation, and a floor re-tuned on one observation
  would be tuned to a transient.
alternatives:
  - option: Re-tune the as-of-night variance floor so F4/F8 do not qualify
    why_not: Tuning a floor against an ordering it produced is fitting to an observed
      outcome by the least visible route in the system. Forbidden by the PR-2/#5700
      do_not_redo and by the override's own terms; the sparse-but-variable pass is the
      floor's registered acceptance test, not a symptom.
  - option: Drop F4 and F8 ad hoc from the family set
    why_not: A hand-removal justified by one night's separation table is a fitted
      choice wearing a structural costume, and it is unfalsifiable — nothing records
      what would have had to be true for them to stay.
  - option: Weight families by their measured discrimination
    why_not: That is C2, and C2 is REFUSED — PR-2 (#5700) found zero lawful folds, 67
      graded dates short. Deriving weights from tonight's dispersion is precisely the
      weakened-fit fallback the arena was built to refuse.
  - option: Treat it as nothing and stop measuring
    why_not: Five active families reading as five independent votes when three are
      doing the work is a real misreading risk for anyone auditing an order. The honest
      response is instrumentation, not silence — which is what w3 is being handed.
evidence:
  - "research/prophet_fusion/FUSION_BOARD_COMPARISON.md family-separation table over the
    2026-08-13 board (69 rows): F8_ATTENTION_CROWDING 2 distinct values, modal 50.00 on
    99% of rows; F4_CATALYST_EVENT 2 distinct, modal 49.28 on 97%; F5_FLOW_POSITIONING
    3 distinct, modal 43.84 on 74%; F1_TECHNICAL_CONFLUENCE 3 distinct, modal 76.98 on
    48%; F2_MOMENTUM_EXTENSION 56 distinct over 69 rows, modal share 4%"
  - "So the ordering work on that pool is mostly F2, then F1 and F5 — stated in the
    override handoff as the honest limit to carry forward"
  - "Frame-dependence of admissibility, same code and thresholds: live buy pool admits
    7/8 members with F1 ACTIVE (tier_cascade ~1.00); the frozen 24-date research frame
    admits 6 with F1 ABSENT (tier_cascade 0.25). One board is one observation."
  - "PR #5700 / research/prophet_fusion/PR2_C2_REDUNDANCY.md — C2 refused
    (refused_no_lawful_folds), zero fitted coefficients, 67 graded dates short"
affects:
  - WS:PROPHET-CONDITIONAL-FUSION
  - engine/us_prophet_fusion.py
  - config/families.yml
  - research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md
confidence: high
reversibility: easy
reversibility_detail: >
  Nothing is changed by this decision, so there is nothing to undo — it forbids a class
  of change and hands a measurement to w3. If w3's diagnostics show the near-constancy
  is persistent rather than pool-specific, that is a REGISTRY revision taken on
  pre-registered terms with its own record, not a re-tune of this floor against this
  board.
decided_by: ceo-sol
decided_at: 2026-08-15
---

## The distinction this record exists to hold

**Admissible** — does this member vary enough tonight to be capable of carrying
information? Owned by the presence and variance floors, evaluated as-of-night,
feature-only, blind to outcomes and blind to the resulting order.

**Discriminating** — did this family actually separate names on this pool? A
measurement about coverage on one night. Visible in the separation table, instrumented
further by w3.

A family can be the first without being the second, and that is not a contradiction —
it is what a sparse-but-variable flag looks like on a night it barely fires. Collapsing
the two is how a floor gets re-tuned against an ordering, which is why they are named
separately here.

## Binding on w3

w3 may **measure** discrimination and must **publish** it. w3 may **not** use those
measurements to reweight C1, to gate a family, or to justify a fitted rung — see
[[DEC-PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER]] for what the override does and does
not authorize. `DNR:KILL-FUSED-COMPOSITE` and `DNR:KILL-POSITIONING-FUSION` continue to
fence the count-style constructions out by name.
