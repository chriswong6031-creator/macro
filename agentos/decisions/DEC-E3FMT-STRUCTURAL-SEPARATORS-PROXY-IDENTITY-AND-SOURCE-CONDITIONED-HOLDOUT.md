---
key: E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT
question: >
  What single deterministic source-format law should govern TFG after the independently frozen
  development corpus proved literal terminal cues, sparse role metadata, proxy questioners and
  same-revision role conflicts, and how should development/holdout success be graded without
  rewarding identity guesses?
answer: >
  Use one transcript-local source-evidence normalization method inside the existing deterministic
  Q&A compiler path. Treat each unambiguous question-bearing Operator handoff followed by a
  non-housekeeping source turn as a structural separator independent of whether the questioner can
  be canonicalized. Direct Operator-name to next-speaker equality is source-supported. A differing
  full-name next speaker is source-supported only when that speaker's first source utterance
  explicitly states an on-for/sitting-in-for relation to the Operator-named principal; the proxy's
  affiliation remains unresolved unless independently stated. All other name disagreements and
  placeholders stay separator-only typed refusals, and spans may never merge across them.
  Respondent role evidence may come only from the same exact transcript revision: answer-segment
  role, replayable participant/title declarations, or a compatible combination. Explicit conflicts
  fail closed; absent role support remains an identity refusal. Accepted respondent role remains
  non-null and source-supported; no external biography, fuzzy person lookup, cross-revision title
  carry-forward or generated Management/CEO/CFO title is permitted. A roster-derived role may use
  the frozen optional nested qa_respondent_identity_evidence.v1 variant with replayable same-revision
  role spans; no new Q&A/person/transcript store, new top-level workspace key, model router or
  qa_exchange.v2 is authorized. Grade TFG against pre-adjudicated source truth: every independently
  source-clean development call must reconstruct, source-conflicted calls must refuse only for their
  frozen source reason, and the unseen holdout must be source-adjudicated after implementation-head
  freeze but before compiler output. At least six of eight fixed holdout slots must be source-clean
  for adequate power; if powered, the frozen compiler must succeed on every clean slot. Never replace
  a dirty/no-QA/mismatched holdout slot and never change code after holdout unseal.
rationale: >
  TFG-0 selected 16 exact development revisions from 2,909 eligible held calls by a hash law frozen
  before body inspection. All 16 byte-replayed and the unchanged parser succeeded on 0/16. Across
  1,524 segments, 672 roles are blank; SCCO and COF have roleless management but replayable
  same-revision participant/title evidence, while ARRY and CTRE contain explicit same-revision role
  conflicts. Post-freeze source adjudication found 110 real question handoffs: 95 direct matches,
  six explicit full-name proxy handoffs and nine unresolved questioner handoffs. Exactly ten calls
  are source-clean under the all-or-nothing canonicalization law. Therefore terminal-phrase
  expansion is not a general method, segment role is evidence rather than unquestioned authority,
  and the earlier >=12/16 outcome bar was impossible without guessing identity or changing
  publication semantics. Structural separation preserves Q&A geometry while source-conditioned
  grading keeps both development and unseen holdout scientifically strict.
alternatives:
  - option: Add more terminal phrases such as line-open, proceed and may-proceed to the current boundary regex.
    why_not: Rejected; terminal phrases appear in opening/presentation housekeeping and do not positively bind a real question handoff.
  - option: Trust any non-empty segment role and ignore transcript-local title text.
    why_not: Rejected; the frozen corpus contains direct same-revision role metadata/title-text conflicts.
  - option: Make canonical respondent role optional or fill roleless speakers with Management.
    why_not: Rejected; current qa_exchange.v1 promises source-supported respondent identity and this would erase rather than solve the evidence problem.
  - option: Use external biographies, fuzzy names, nickname maps or prior-quarter titles.
    why_not: Rejected; those create cross-source/time/revision inference and are not support from the exact transcript being compiled.
  - option: Keep >=12/16 development and bare >=6/8 holdout outcome bars.
    why_not: Rejected; the independently adjudicated development source-clean ceiling is ten calls, so the former bar would reward guessing; six of eight is retained only as a pre-compiler holdout power gate.
  - option: Drop unresolved question handoffs entirely.
    why_not: Rejected; adjacent accepted Q&A spans could then be merged across a real but unresolved structural boundary.
evidence:
  - research/earnings_intelligence/e3/tfg0_transcript_format_census_receipt.json
  - research/earnings_intelligence/e3/tfg0_development_boundary_identity_adjudication.json
  - research/earnings_intelligence/e3/tfg0_respondent_identity_feasibility_receipt.json
  - research/earnings_intelligence/e3/TFG0_R1_BOUNDARY_IDENTITY_AND_HOLDOUT_SCORING_AMENDMENT_2026-08-27.md
  - research/earnings_intelligence/e3/TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md
  - research/earnings_intelligence/e3/tfg1_transcript_format_holdout_selection.json
affects:
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
  - E3-FMT
  - TFG-1
  - E3-C
confidence: high
reversibility: costly
decided_by: sol
decided_at: 2026-08-27
supersedes:
  - DEC:E3FMT-TRANSCRIPT-LOCAL-SOURCE-EVIDENCE-NORMALIZATION
---

# Canonical R1 details

## Structural separator vs mintable identity

All 110 adjudicated development question handoffs are structural separators. A separator remains
load-bearing when its person identity refuses: it divides windows so adjacent accepted exchanges
cannot absorb its source text. An unresolved separator cannot mint canonical Q&A and does not grant
partial-publication authority in TFG-1.

Direct questioner identity requires exact name equality after case/whitespace/honorific normalization
only. A differing full-name next speaker is accepted only with an explicit same-utterance on-for /
sitting-in-for relation. The principal's affiliation never transfers automatically to the proxy.
Structured placeholders, first-name-only self-identification and one-character spelling disagreements
remain unresolved; no edit distance or nickname repair.

## Closed role comparison law

Role normalization exists only to compare two explicit same-revision source values. Exact V1 alias
families are:

- `CEO` <-> `Chief Executive Officer`
- `CFO` <-> `Chief Financial Officer`
- `COO` <-> `Chief Operating Officer`

There is no `CIO` alias and no open-ended `etc.`. Other roles compare only as exact normalized title
components. A compound replayed source title may split only on explicit comma, semicolon, slash or
`and`. Compatible nonblank answer-segment role preserves that exact source role string. Blank
answer-segment role plus replayable roster/title support preserves the normalized full source title
phrase. Explicit incompatible evidence fails `management_identity_conflict`; missing support fails
`management_identity_insufficient`.

## Development gate

TFG-1 must replay all 16 exact SHAs; recover 110/110 structural separators with zero
opening/queue/closing false positives; resolve all 101 source-supported direct/proxy questioners;
keep all 9 unresolved handoffs separator-only/refused without adjacent contamination; reconstruct
all 10 frozen source-clean calls; and make the remaining six calls fail only for their frozen
source-identity/conflict reason. AAPL remains exactly 7/26/68. Accepted unsupported=0,
cross-event=0 and accepted replay=100%.

## Unseen holdout gate

The eight metadata/SHA-frozen ranks 17-24 remain unopened. After development is green, freeze the
implementation head, then open the eight exact revisions and, **before any compiler output**, freeze
a source-only adjudication for each fixed slot: `QNA_SOURCE_CLEAN`, `QNA_SOURCE_CONFLICTED`,
`NO_QA_ADMISSION`, or `SOURCE_REVISION_MISMATCH`. Never replace/skip/rerank. Fewer than 6/8 clean =>
`INSUFFICIENT_HOLDOUT_POWER`. Otherwise the already-frozen compiler must succeed on every clean slot,
preserve separators and pre-adjudicated refusal reasons on conflicted slots, create no false Q&A on
no-QA slots, and keep hard safety green. No code change is permitted after holdout unseal.

This decision grants no production revision, publication, Terminal, model, scoring, FIF/Prophet or
E3-P authority. TFG-1 remains production-unarmed; a later fresh untouched-production-OOS operation
is still required to close parent E3-C.
