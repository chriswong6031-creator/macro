---
key: E3FMT-ABSENCE-OF-ROLE-CONFLICT-IS-NOT-SOURCE-CLEAN
claim: >
  TFG-1's second development-gold falsifier lives in the source-clean DEFINITION, one layer below the
  first falsifier's structural counts: the ratified R2 gold graded ARQQ/2026Q2 and FANG/2026Q2
  source-clean because no role conflict was found, but the frozen respondent identity-evidence
  amendment requires POSITIVE replayable same-revision role/title support, so absence of conflict is
  not cleanliness and the true clean set is 7 of 16 calls, not 9 — while three further calls (BANR,
  LTH, HTGC) carry undeclared role conflicts, making 5 conflict calls rather than 2.
falsifier: >
  Read research/earnings_intelligence/e3/TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md
  "Closed nested contract" section. If it does not state that missing role/title support is a refusal
  (management_identity_insufficient) and that no accepted extended respondent may have an empty role,
  the claim falls. Then re-read the ARQQ and FANG rows of
  research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r2.json: if either
  carries same-revision role/title evidence for its management respondent, the D2 correction falls.
so_what: >
  When a pre-registered gold declares a derived SET (source-clean calls, eligible slots, admitted
  cases), re-derive that set from the frozen predicate before ratifying it — do not ratify the set and
  the predicate as independent facts. A definition error inside an internally coherent gold passes
  every internal consistency check: the R2 gold's own totals reconciled exactly (113 = 97 + 6 + 10)
  and were verified twice, yet its clean set still contradicted the law it was encoding, and only
  implementing against real source exposed it. For any single-use holdout this is load-bearing rather
  than cosmetic: the holdout's source-only adjudication must freeze its clean predicate BEFORE
  compiler output, so a clean definition that counts role conflict but not role absence adjudicates
  untitled-executive slots clean and calibrates the power ruling on the wrong denominator — an error
  that is unrepairable afterwards because the holdout is non-replaceable. Concretely: write a
  cleanliness predicate as positive support AND no contradiction, never as no-contradiction alone.
kind: constraint
verified_at: 2026-08-28
verified_by: >
  Macro PR #6591 (CLOSED UNMERGED, head 77fd9411c9cfb799b245c8138d2f1a40052d3b8d) measured the 16
  development revisions and reported D1/D2; Sol review #5048161769 (CHANGES_REQUESTED,
  2026-08-28T05:27:16Z) accepted both and ruled the operation terminal
  STOPPED_AT_DEVELOPMENT_GATE — SECOND GOLD FALSIFIER. Named source evidence: BANR declares Jill Rice
  "our Chief Credit Officer" in segment #1 while tagging her CFO; LTH declares Erik Weaver
  "Executive Vice President and CFO" while tagging him CEO; HTGC declares Seth Meyer "President"
  while tagging him CEO; ARQQ's Nick Pointon answers 8 times with a blank role and only
  "let me turn the call over to Nick Pointon"; FANG's Chad McAllaster answers with a blank role and
  only "I'll let Chad or Danny give the details". Corrected partition recorded in
  research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json.
scope:
  - macro
  - research/earnings_intelligence/e3/**
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
  - E3-FMT
confidence: verified
---

# Why this was invisible to internal gold checks

The R2 gold was checked twice at pickup and passed both times. Internally, every declared total
recomputed from `per_call` and the direct/proxy/unresolved classes partitioned each call exactly.
Externally, 16/16 revisions replayed byte-identically and all 113 separator sets matched the
detector. None of that can catch a wrong *predicate*: the clean set was stored as a literal list of
pairs, so it was consistent with itself no matter which rule produced it.

The gold's structural half and its respondent-role half also failed for different reasons, which is
why one correction did not surface the other. The first falsifier was an **omission** — three real
separators the gold left out, detectable by recovering more separators than the gold declared. The
second is a **definitional** error: ARQQ and FANG have no missing structure at all. ARQQ has a single
clean separator and FANG has fourteen, all direct exact-name matches, and both calls therefore look
maximally clean from the questioner side. They fail only on the respondent side, and only against a
rule the gold never re-derived.

# The trap for the next wave

Two escape hatches look available at the moment of discovery and are both closed:

- **Publishing the answer with an empty or generic role.** `qa_exchange.v1` requires a non-empty
  source-supported role, and the amendment explicitly bars an accepted extended respondent with an
  empty role. Emitting `Management` would convert a missing fact into a label.
- **Relaxing conflict detection so the three new conflicts disappear.** The same relaxation also
  stops detecting the already-ratified ARRY and CTRE conflicts, so it trades a smaller falsifier for
  a larger one.

The closed alias table is part of this: CEO/CFO/COO only, with CIO deliberately excluded precisely
because CTRE tags its Chief Investment Officer as CFO. Widening the aliases to absorb the new
conflicts would silently re-admit CTRE.

# Cross-cutting reading

The general form is the reason this is worth remembering outside E3: **a derived set stored as a
literal is not evidence of the rule that was supposed to derive it.** Any prereg that freezes both a
predicate and the population it selects should carry the derivation, not just the result, so a
later reader can replay the selection instead of trusting it.
