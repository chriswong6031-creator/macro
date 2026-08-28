---
key: E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN
question: >
  TFG-1 R2 implemented the ratified R2 development gold faithfully and then found the gold and the
  exact source disagreeing in two further places: the gold declares two calls with explicit
  management role conflict where the source shows five, and two calls inside the source-clean nine
  contain management the revision never gives an office at all. What development truth governs the
  successor implementation, and what does QNA_SOURCE_CLEAN actually mean?
answer: >
  Ratify an R3 development adjudication. Separator and questioner truth carry forward unchanged at
  113 structural separators, 97 direct questioners, 6 explicit full-name proxies, 103 source-supported
  questioners and 10 unresolved questioners. Explicit management-role-conflict calls are exactly five —
  ARRY, CTRE, BANR, LTH, HTGC. ARQQ/2026Q2 and FANG/2026Q2 leave the source-clean set because their
  exact revisions do not positively source-support a non-empty respondent role for a management answer
  inside a Q&A window. The source-clean full-call set is therefore exactly seven — OCSL/2026Q3,
  GEF/2026Q3, UPBD/2026Q2, SCCO/2026Q2, AGM/2026Q2, COF/2026Q2, KREF/2026Q2 — and the refusal set is
  exactly nine. Source blockers are recorded as SETS, never as an order-dependent single first-failure
  reason: CTRE, LTH, BANR and HTGC each carry unresolved-questioner AND management-role-conflict
  simultaneously. QNA_SOURCE_CLEAN now requires POSITIVE replayable same-revision respondent role/title
  support for every accepted management answer, plus no incompatible same-revision role evidence;
  absence of conflict alone is not clean. Every other method, identity, proxy, correction, holdout,
  no-rescue and production-admission law is unchanged, AAPL remains 7/26/68, production revision
  admission remains AAPL-only, and the eight-slot holdout stays sealed at holdout_bodies_inspected: 0.
rationale: >
  The old definition tested for the presence of contradictory role evidence and therefore could not
  see the absence of any role evidence at all. That is a definitional gap, not carelessness: the R2
  partition is internally self-consistent under its own rule ("no unresolved questioner AND no
  contradictory role evidence") and reproduces 9/7 exactly. ARQQ's Nick Pointon speaks eight times
  with a blank role and is only ever introduced as "let me turn the call over to Nick Pointon";
  FANG's Chad McAllaster speaks once, role blank, introduced as "I'll let Chad or Danny give the
  details". Under the already-frozen amendment requiring a non-null source-supported respondent role,
  neither call can produce a supported respondent, so the frozen gate "9/9 source-clean calls
  reconstruct non-empty" was not satisfiable as written. The correction makes the gate STRICTER, not
  looser, which is why it is safe to ratify without re-opening the method.
  The set-valued blocker law matters for the same reason the count did: an order-dependent first
  failure hides the other true blockers behind whichever one the implementation happens to evaluate
  first, so a correct implementation and a wrong one can produce the same single-reason receipt.
  Deferring this past the implementation-head freeze was the unacceptable option. The holdout's
  source-only slot adjudication must be frozen BEFORE any compiler output using a definition of
  QNA_SOURCE_CLEAN. Had that definition counted role conflict but not role absence, holdout slots
  containing an untitled executive would have been adjudicated clean, the compiler would have missed
  them, and the power ruling would have been calibrated on the wrong denominator — spending a
  single-use, non-replaceable holdout under a definition the development corpus had already shown to
  be incomplete. That error cannot be undone; a round trip can.
alternatives:
  - option: Amend the gold inside the R2 operation and continue to the freeze and holdout
    why_not: >
      R2's canonical handoff says STOP without rescue if any frozen source-clean call fails. Two do.
      Self-amending the grading truth inside the operation being graded is precisely the move the v1
      wave refused, and it would have put a corrected gold and an unfrozen implementation in the same
      uninspectable commit.
  - option: Relax conflict detection so the gold's declared two-conflict count becomes correct
    why_not: >
      BANR, LTH and HTGC carry the same construction as ARRY and CTRE — a same-segment declared title
      contradicting every segment role tag. Any relaxation that stopped detecting the three would also
      stop detecting the two the gold already accepts, weakening the method to fit a receipt.
  - option: Accept an empty respondent role for ARQQ and FANG
    why_not: >
      Breaks qa_exchange.v1, whose accepted respondent role is non-null and source-supported. Making
      role nullable to rescue two development calls would silently widen what the compiler may publish.
  - option: Fill the missing roles from a first name, a prior quarter, or an external source
    why_not: >
      Guessed identity. Explicitly forbidden by the frozen identity law and by every prior TFG ruling.
  - option: Defer the correction until after the implementation-head freeze
    why_not: >
      The holdout source-only adjudication is frozen before compiler output and depends on this exact
      definition. Deferring risks spending the single-use holdout against a definition already known
      to be incomplete.
evidence:
  - PR 6591 head 77fd9411c9cfb799b245c8138d2f1a40052d3b8d, CLOSED UNMERGED, Sol review 5048161769
  - Sol STOP ruling, Slack #agent-dispatch 1787894855.465139, terminal at second gold falsifier
  - research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json
  - research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r2.json preserved unchanged at blob 9017d327fd942a33f7716c8e0a86f72311a43131
  - Re-derived independently by summation over the R2 per_call block — 113 handoffs / 97 direct / 6 proxy / 10 unresolved / 103 supported, and exactly six calls carrying unresolved indices (BANR, CTRE, HTGC, LTH, MBLY, TRVI)
affects:
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
  - research/earnings_intelligence/e3/**
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-28
---

Ratified by Sol on the `tfg1-r3-gold-source-clean-correction-20260828-v1` carrier after TFG-1 R2
terminated `STOPPED_AT_DEVELOPMENT_GATE — SECOND GOLD FALSIFIER`.

This is a source-gold correction, not threshold tuning. It supersedes
[[DEC-E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS]] on the management-role-conflict set, the
source-clean/refusal partition, and the introduction of set-valued blockers only. Everything that
record established about structural separators and questioner identity carries forward unchanged.

The corrected per-call blocker sets are:

| call | source blockers |
| --- | --- |
| MBLY/2026Q2 | unresolved_questioner |
| ARQQ/2026Q2 | missing_same_revision_respondent_role_support |
| TRVI/2026Q2 | unresolved_questioner |
| CTRE/2026Q2 | unresolved_questioner, management_role_conflict |
| LTH/2026Q2 | unresolved_questioner, management_role_conflict |
| BANR/2026Q2 | unresolved_questioner, management_role_conflict |
| FANG/2026Q2 | missing_same_revision_respondent_role_support |
| HTGC/2026Q2 | unresolved_questioner, management_role_conflict |
| ARRY/2026Q2 | management_role_conflict |

Successor implementation operation: `tfg1-r3-deterministic-transcript-format-hardening-20260828-v1`.
It is NOT started by this record and requires its own commission.

Related: [[DSC-E3FMT-ABSENCE-OF-ROLE-CONFLICT-IS-NOT-SOURCE-CLEAN]],
[[DEC-E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT]].
