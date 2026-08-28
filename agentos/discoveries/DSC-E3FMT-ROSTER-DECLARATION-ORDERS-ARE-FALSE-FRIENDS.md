---
key: E3FMT-ROSTER-DECLARATION-ORDERS-ARE-FALSE-FRIENDS
claim: >
  Earnings-call participant rosters are declared in two orders that are false friends for
  each other -- name-first ("Kevin Hostetler, our CEO") and office-first ("our CEO, Matt
  Salem") -- and parsing one with the other's pattern yields a confident WRONG role
  binding rather than no binding.
falsifier: >
  Find an earnings transcript whose participant roster uses neither order, or show that a
  parser without the per-sentence order decision reproduces the frozen 16-call
  adjudication (16/16 separator sets, 7/7 non-clean refusing for their frozen reasons)
  without falsely refusing any source-clean call.
so_what: >
  Every one of these failure modes produces a fabricated management_identity_conflict on a
  call whose source is perfectly consistent, which reads as a real source defect and would
  be escalated as one. Any future roster/title parser in this repo must be built against
  the corpus rather than from first principles, and must be regression-checked for FALSE
  conflicts on calls known to be clean -- not only for missed bindings on calls known to
  be dirty.
kind: landmine
verified_at: 2026-08-28
verified_by: "engine/company_intelligence/qa_reconstruction.py; tests/test_company_intelligence_qa_tfg1_r2.py; PR #6591"
scope:
  - macro
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
  - engine/company_intelligence/**
confidence: verified
---

Four distinct bugs, all measured on the 16 frozen development revisions:

1. Order confusion. Parsing ARRY (name-first) with the office-first pattern binds Keith
   Jennings to CEO when the source says CFO — erasing a real ratified role conflict.
2. A title must BEGIN with an office word once determiners and possessives are stripped.
   Without that anchor, "Ole Rosgaard, will provide a strategy and market update" parses
   as a title merely because CFO appears later in the same sentence.
3. The office head must be anchored inside the office-first pattern, not validated after
   it. KREF's "joined on the call by our CEO, Matt Salem" matched title="call by our CEO"
   via the earlier "the", failed validation, and took the real declaration down with it.
4. A candidate name must not itself be an office phrase. "Chief Development Officer," is
   three capitalised tokens followed by a comma, so it was read as a person and truncated
   the previous speaker's title to nothing. Honorific periods are not sentence ends
   either — splitting after "Dr." severs a declaration from its title.

Possessives must be stripped case-insensitively: requiring a capitalised possessive
silently dropped "the company's Chief Executive Officer".

Each bug was found by running the 16-call adjudication and reading the raw declaration
text of every call that refused unexpectedly. The first three were invisible from the code
alone and presented as source defects.

The closed CEO/CFO/COO alias table earns its exclusion of CIO here: CTRE declares James
Callister "Chief Investment Officer" and tags his segments CFO. An open-ended abbreviation
rule would alias that away and erase one of the corpus's two ratified role conflicts.

Related: [[DSC-E3FMT-R2-GOLD-UNDERCOUNTS-ROLE-CONFLICTS-AND-OVERCOUNTS-CLEAN]] — the
residual disagreements that survived after all four parser bugs were fixed.
