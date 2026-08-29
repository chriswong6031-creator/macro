---
key: E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN
question: >
  R2 terminated at a SECOND development-gold falsifier: the ratified R2 gold declares two
  management-role-conflict calls and nine source-clean calls, but the source shows five conflicts
  and only seven calls with positive same-revision respondent role support. What development truth
  governs the R3 implementation, and what does QNA_SOURCE_CLEAN actually require, without weakening
  the method or spending the unseen holdout?
answer: >
  Ratify an R3 development adjudication that carries the entire structural layer over verbatim -
  113 structural separators, 97 direct questioners, 6 explicit full-name proxies, 103 source-supported
  questioners, 10 unresolved questioners - and corrects only the respondent-role layer.
  Management-role-conflict calls are exactly five: ARRY, CTRE, BANR, LTH, HTGC. Source-clean calls
  are exactly seven: OCSL/2026Q3, GEF/2026Q3, UPBD/2026Q2, SCCO/2026Q2, AGM/2026Q2, COF/2026Q2,
  KREF/2026Q2. ARQQ/2026Q2 and FANG/2026Q2 leave the source-clean set. The refusal set is therefore
  exactly nine: MBLY, ARQQ, TRVI, CTRE, LTH, BANR, FANG, HTGC, ARRY. QNA_SOURCE_CLEAN requires
  POSITIVE replayable same-revision respondent role/title support for every accepted management
  answer AND no incompatible same-revision role evidence - absence of conflict is not cleanliness.
  Per-call refusal reasons are recorded as SETS, never as one order-dependent first failure.
  Machine grading truth becomes
  research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json.
  The R2 adjudication and DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS are preserved
  byte-unchanged as falsified experimental evidence; the R2 structural correction remains binding
  and is not withdrawn. The eight-call holdout stays SEALED at holdout_bodies_inspected 0.
rationale: >
  R2 classified ARQQ and FANG source-clean because no role conflict existed for their management
  respondents. That is the wrong test. Both respondents answer inside the Q&A window with a BLANK
  segment role and no same-revision roster or title declaration binding them to any office, so a
  qa_exchange.v1 object minted from those answers would publish a respondent with no replayable
  source support. Absence of contradicting evidence is not positive evidence. Symmetrically, three
  further calls do carry explicit incompatible evidence that R2 missed: BANR declares Jill Rice
  "our Chief Credit Officer" while tagging her answer segments CFO; LTH declares Erik Weaver
  "Executive Vice President and CFO" while tagging his CEO; HTGC declares Seth Meyer "President"
  while tagging his CEO. None of the three is reconcilable through the closed CEO/CFO/COO alias
  table. The corrected partition follows mechanically, and it moves in the conservative direction:
  strictly fewer calls are trusted for full-call reconstruction than R2 believed.
  The discriminator that makes this a real method requirement rather than a blanket rule is that
  SCCO and COF ALSO publish blank segment roles yet remain source-clean, because their revisions
  carry replayable same-revision title declarations ("Andrew Young, Capital One's Chief Financial
  Officer"). A parser that refuses every blank segment role is exactly as wrong as one that accepts
  every blank segment role.
alternatives:
  - option: Keep the ratified R2 nine-call clean set because it was already Sol-ratified.
    why_not: >
      Rejected. A ratified gold that the source contradicts is a falsified gold. Preserving it as
      the grading target would train the R3 implementation to publish two respondents with no
      replayable role support, which is the exact contract violation the respondent-identity
      amendment exists to prevent.
  - option: Fill the blank ARQQ/FANG roles from context or an external roster.
    why_not: >
      Rejected. That is guessed identity. The frozen method forbids model/fuzzy/external identity
      repair, and a filled role is indistinguishable downstream from a source-supported one.
  - option: Relax conflict detection so BANR, LTH and HTGC clear.
    why_not: >
      Rejected. Any relaxation broad enough to clear "Chief Credit Officer vs CFO" and
      "President vs CEO" also stops detecting ARRY and CTRE, which are already-frozen conflicts.
      The falsifier would be traded for a regression.
  - option: Widen the closed CEO/CFO/COO alias table to absorb the three new conflicts.
    why_not: >
      Rejected. CIO is excluded on purpose - CTRE tags its Chief Investment Officer as CFO - so
      widening the table silently re-admits CTRE and ARRY as clean.
  - option: Open the sealed holdout to decide which definition generalizes better.
    why_not: >
      Rejected. The holdout is single-use evidence and may not be spent before corrected development
      truth is ratified and an implementation head is frozen.
  - option: Record one scalar refusal reason per call, as R2 implied.
    why_not: >
      Rejected. CTRE, LTH, BANR and HTGC each carry BOTH unresolved_questioner and
      management_role_conflict. A scalar reason hides real blockers and makes the grading gate
      depend on evaluation order rather than on source truth.
evidence:
  - research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json
  - research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r2.json
  - research/earnings_intelligence/e3/TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md
  - research/earnings_intelligence/e3/tfg0_transcript_format_development_corpus_selection.json
  - "Macro PR #6591; Sol review #5048161769 on head 77fd9411c9cfb799b245c8138d2f1a40052d3b8d (CHANGES_REQUESTED, 2026-08-28T05:27:16Z), accepting falsifiers D1 and D2"
  - "Source re-verification, this carrier: 7/7 development bodies re-fetched and sha256-matched against the frozen selection receipt; all five conflicts and both missing-role findings re-derived from segment arrays; holdout_revisions_touched 0"
affects:
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
  - E3-FMT
  - TFG-1
  - E3-C
confidence: high
reversibility: costly
decided_by: sol
decided_at: 2026-08-28
---

# Scope of amendment

This is a **partial development-gold correction**, not a new TFG method and not a compiler change.
It replaces only the management respondent-role conflict count, the source-clean/refusal partition
implied by it, and the representation of per-call refusal reasons as SETS.

`DEC:E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT` remains controlling
for structural separators, direct/proxy identity, fail-closed behavior, holdout use, production
authority and every no-rescue boundary.

`DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS` is **not withdrawn**. Its structural
correction — the three omitted combined Q&A-opener-plus-first-question handoffs and the resulting
113/97/6/103/10 counts — is carried forward here verbatim and remains binding. That record and the
R2 adjudication JSON are preserved byte-unchanged as falsified experimental evidence, exactly as
the TFG-0 110-separator receipt was preserved after the first falsifier. Neither is ever edited to
conceal a falsifier.

## The corrected law

`QNA_SOURCE_CLEAN` — a call is source-clean for full-call reconstruction only when:

1. every real questioner handoff is source-supported under the frozen direct/proxy law; **and**
2. every management answer that would be accepted into `qa_exchange.v1` has **positive replayable
   same-revision** respondent role/title support; **and**
3. no incompatible same-revision role evidence exists for that respondent.

Condition 2 is the correction. **Absence of conflict is not cleanliness.**

## Ratified R3 development gates

The R3 implementation must:

- replay the exact 16 development revisions under the canonical-JSON SHA convention;
- recover **113/113** structural separators with zero opening/queue/closing false positives;
- resolve **103/103** source-supported direct/proxy questioners;
- keep **10/10** unresolved questioners separator-only/refused with zero adjacent contamination;
- reconstruct all **7/7** source-clean full calls;
- make the remaining **9** calls fail for **exactly their frozen source blocker SET** and no other
  reason;
- preserve AAPL exactly **7 exchanges / 26 management answer turns / 68 replay spans**;
- keep accepted unsupported = 0, cross-event contamination = 0, accepted replay = 100%;
- preserve zero ticker/provider branches, model identity inference, new stores, schema forks or
  production-admission widening.

## Frozen per-call blocker sets

| Call | Blocker set |
|---|---|
| `MBLY/2026Q2` | `unresolved_questioner` |
| `ARQQ/2026Q2` | `missing_same_revision_respondent_role_support` |
| `TRVI/2026Q2` | `unresolved_questioner` |
| `CTRE/2026Q2` | `management_role_conflict`, `unresolved_questioner` |
| `LTH/2026Q2` | `management_role_conflict`, `unresolved_questioner` |
| `BANR/2026Q2` | `management_role_conflict`, `unresolved_questioner` |
| `FANG/2026Q2` | `missing_same_revision_respondent_role_support` |
| `HTGC/2026Q2` | `management_role_conflict`, `unresolved_questioner` |
| `ARRY/2026Q2` | `management_role_conflict` |

## Holdout

Unchanged and SEALED. Ranks 17–24 stay unopened at `holdout_bodies_inspected: 0` until every
corrected development gate is green and an exact implementation head is frozen. The corrected
definition is strictly narrower than R2's, so it can only LOWER the holdout clean count: an
`INSUFFICIENT_HOLDOUT_POWER` stop under it is a legitimate scientific outcome and must **not** be
rescued by reverting to the falsified absence-of-conflict definition.

## Operation identity

`tfg1-r2-deterministic-transcript-format-hardening-20260827-v1` terminates at its accepted second
gold falsifier and is never reused. The successor implementation is a new logical operation:

`tfg1-r3-deterministic-transcript-format-hardening-20260828-v1`

It is **NOT_BUILT**. No implementation starts from this decision alone; it begins only after this
records correction lands and one bounded worker is commissioned under the active R3 handoff.
