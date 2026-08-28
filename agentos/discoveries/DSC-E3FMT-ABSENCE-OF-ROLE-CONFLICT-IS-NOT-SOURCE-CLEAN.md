---
key: E3FMT-ABSENCE-OF-ROLE-CONFLICT-IS-NOT-SOURCE-CLEAN
claim: >
  A source-cleanliness rule written as "no contradictory role evidence" cannot see a speaker with NO
  role evidence at all, so a corpus partition built on it silently admits calls that can never produce
  a source-supported respondent — the defect is invisible until an implementation is graded against it.
falsifier: >
  Open the exact revisions for ARQQ/2026Q2 and FANG/2026Q2 and find any same-revision positive
  role/title support for Nick Pointon or Chad McAllaster. There is none: Pointon speaks 8x with a
  blank role and is introduced only as "let me turn the call over to Nick Pointon"; McAllaster speaks
  once (#92), role blank, introduced only as "I'll let Chad or Danny give the details". If either
  carried a same-revision title, that call would be legitimately source-clean and this claim fails.
so_what: >
  When freezing any source-conditioned partition, write the rule as a POSITIVE support requirement,
  not as the absence of a contradiction. The two are not complements: absence-of-conflict is satisfied
  by absence-of-evidence, which is the exact case that breaks downstream acceptance. For TFG
  specifically, the holdout's source-only slot adjudication is frozen BEFORE compiler output using
  this definition, so a conflict-only definition would adjudicate a slot with an untitled executive as
  clean, the compiler would miss it, and the power ruling would be calibrated on the wrong denominator
  — spending a single-use, non-replaceable holdout under a definition already known to be incomplete.
kind: constraint
verified_at: 2026-08-28
verified_by: >
  PR 6591 head 77fd9411c9cfb799b245c8138d2f1a40052d3b8d (CLOSED UNMERGED) DECISION_REQUEST D2;
  Sol review 5048161769; ratified in
  research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json
scope:
  - macro
  - research/earnings_intelligence/e3/**
  - engine/company_intelligence/**
confidence: verified
---

Found by the second TFG-1 implementation wave, which measured the ratified gold against source
before encoding it rather than trusting it — the same discipline that produced the first falsifier.

The R2 partition is internally self-consistent under its own stated rule ("no unresolved questioner
AND no contradictory role evidence") and reproduces its 9/7 split exactly. That is what makes this
class of defect dangerous: the receipt is coherent, reproducible, and wrong only against source.

Two independent lessons for future frozen partitions:

**Positive support, not absent contradiction.** Any acceptance rule whose downstream consumer needs
a non-null value must be phrased as a requirement for that value. Phrasing it as the absence of a
conflicting value silently admits the empty case.

**Blockers are sets.** The same wave showed that an order-dependent single first-failure reason hides
every other true blocker behind whichever one the implementation evaluates first — so a correct
implementation and an incorrect one can emit the same single-reason receipt. CTRE, LTH, BANR and HTGC
each genuinely carry both unresolved-questioner and management-role-conflict; recording only the first
would have made three of the nine refusals fail for a reason the gold did not record, which is how the
first falsifier surfaced.

Related: [[DEC-E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN]],
[[DSC-TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES]].
