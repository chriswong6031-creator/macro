---
key: E3FMT-TRANSCRIPT-LOCAL-SOURCE-EVIDENCE-NORMALIZATION
question: >
  After the GOOGL E3-C falsifier and a pre-registered 16-call held-source census show that the
  deterministic Q&A compiler fails across transcript formats, what source-format method may replace
  the AAPL-calibrated literal-boundary / segment-role assumptions without weakening source-supported
  identity or contaminating the next OOS proof?
answer: >
  Use one deterministic transcript-local source-evidence normalization stage inside the existing
  Q&A compiler path. A Q&A boundary is admitted by a named Operator handoff that binds to the next
  non-housekeeping source speaker, never by a terminal phrase such as "go ahead" alone. Questioner
  identity is anchored to that next source speaker; affiliation is parsed only from the admitted
  handoff clause and may remain unresolved. Respondent roles may be supported by the same-revision
  segment role, replayable same-transcript participant/title declarations, or a compatible
  combination. Incompatible source role evidence fails closed; missing role evidence remains an
  identity refusal. No external biography, nickname/fuzzy lookup, issuer/ticker constant or
  cross-revision title carry-forward may fill a role. Accepted respondents remain
  identity_state=source_supported. When role support comes from a transcript roster rather than the
  respondent's answer-segment role, preserve the evidence explicitly through the versioned optional
  nested qa_respondent_identity_evidence.v1 contract with exact same-revision source spans. Legacy
  respondent objects remain valid. Do not silently make role nullable, mint generic Management, add
  a new transcript/Q&A/person store, or invent qa_exchange.v2 on builder judgment.
rationale: >
  TFG-0 selected 16 exact development revisions from 2,909 eligible held calls by a hash law frozen
  before body inspection. All 16 byte-replayed. The unchanged parser succeeded on 0/16: eleven calls
  failed after the literal "go ahead" rule admitted an invalid pre-Q boundary and five had zero
  literal-go-ahead boundaries despite real Q&A. Across 1,524 segments, 672 roles are blank; SCCO and
  COF have no non-housekeeping role labels at all. At the same time, replayable opening rosters in
  multiple calls explicitly identify roleless house speakers, while ARRY and CTRE show that segment
  role metadata can conflict with explicit transcript title text. A larger terminal-phrase whitelist
  therefore fixes neither boundary truth nor respondent provenance. Transcript-local evidence
  normalization uses the source revision we already hold, preserves deterministic replay and gives
  conflicts an honest refusal state.
alternatives:
  - option: Add more terminal phrases such as line-open, proceed and may-proceed to the existing boundary regex.
    why_not: >
      Rejected. Opening housekeeping also contains question language and presentation handoffs. Phrase
      accumulation remains vendor-shaped and does not positively bind a questioner to the next source speaker.
  - option: Trust any non-empty segment role and ignore transcript-local title text.
    why_not: >
      Rejected. The development census contains direct role metadata/title-text conflicts; non-empty
      metadata is evidence, not unquestioned authority.
  - option: Make canonical respondent role optional or fill roleless speakers with Management.
    why_not: >
      Rejected. Current qa_exchange.v1 and Terminal promise source-supported respondent role. Silent
      weakening would change product truth and erase the evidence problem instead of solving it.
  - option: Use external biographies / issuer websites to resolve roles.
    why_not: >
      Rejected. That creates cross-source identity/time/correction problems and can assign a title not
      supported by the exact transcript revision being compiled.
  - option: Source-shop another transcript provider after a format failure.
    why_not: >
      Rejected as method repair. A later independently held source revision may have its own lawful
      receipt, but provider substitution after observing failure does not demonstrate compiler generality.
evidence:
  - "research/earnings_intelligence/e3/tfg0_transcript_format_census_receipt.json — 16/16 exact revisions, 0/16 current compiler success, role/boundary census."
  - "research/earnings_intelligence/e3/tfg0_transcript_format_development_corpus_selection.json — corpus frozen before body inspection."
  - "research/earnings_intelligence/e3/TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_ARCHITECTURE_FREEZE_2026-08-27.md — exact method, null/conflict/correction and proof law."
  - "research/earnings_intelligence/e3/tfg1_transcript_format_holdout_selection.json — eight unseen format revisions frozen with bodies_inspected=0."
  - "engine/company_intelligence/qa_reconstruction.py — current literal go-ahead boundary and role-dependent management classifier."
  - "engine/company_intelligence/qa_exchange.py — accepted respondent name+role+identity_state source-supported contract."
affects:
  - "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
  - "E3-FMT"
  - "TFG-1"
  - "E3-C"
confidence: high
reversibility: costly
decided_by: sol
decided_at: 2026-08-27
superseded_by: "DEC:E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT"
---

# SUPERSEDED BY TFG-0 R1

This initial TFG decision is retained only as provenance for the first post-GOOGL architecture draft. It is formally superseded by:

`DEC:E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT`

The replacement decision is self-contained and is the sole canonical TFG method law. In particular, the provisional `>=12/16` development and bare `>=6/8` holdout outcome bars below are **not active law**; source-only adjudication later proved the development source-clean ceiling is ten calls and replaced both bars with the R1 source-conditioned protocol.

# Historical implementation boundary

This decision was architecture only. It granted no production revision admission and no second-issuer publication authority.

The historical first draft said TFG-1 should remain Macro-only and production-unarmed, preserve the AAPL-only accepted revision gate and AAPL 7/26/68, prove >=12/16 on the declared development corpus, freeze its code head before opening the eight-call holdout, then require >=6/8 on that holdout with no same-carrier post-holdout tuning. Those two numeric outcome bars were provisional and are superseded by the replacement decision. GOOGL remains a known regression only. Fresh E3 second-issuer production acceptance remains a later pre-registered operation; E3-P stays locked.
