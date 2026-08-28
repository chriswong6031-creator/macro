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
  the claim falls. Then refetch ARQQ/2026Q2 and FANG/2026Q2 from
  https://app.mastermind-x.com/data/tx/{TICKER}/2026Q2.json.gz and search the whole revision for any
  title binding Nick Pointon or Chad McAllaster to a role: if either revision carries same-revision
  role/title evidence for its management respondent, the D2 correction falls. Symmetrically, if BANR,
  LTH or HTGC shows no incompatible declared-title-vs-tagged-role pair, D1 falls.
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
  STOPPED_AT_DEVELOPMENT_GATE — SECOND GOLD FALSIFIER. The correction carrier
  tfg1-r3-gold-source-clean-correction-recovery-20260828-v2 then independently re-verified every
  named role fact against source bytes: all seven respondent-layer revisions were refetched from
  https://app.mastermind-x.com/data/tx and re-hashed 7/7 against the frozen body_sha256 in
  tfg0_transcript_format_development_corpus_selection.json, with 0 holdout revisions touched.
  Confirmed: BANR declares Jill Rice "our Chief Credit Officer" (seg 1) while tagging her CFO; LTH
  declares Erik Weaver "Executive Vice President and CFO" (seg 1) while tagging him CEO; HTGC declares
  Seth Meyer "President" (seg 1) while tagging him CEO; CTRE declares James Callister "Chief
  Investment Officer" (seg 2) while tagging him CFO; ARRY declares Neil Manning "our President and
  COO" (seg 1) while tagging him CFO. ARQQ's Nick Pointon answers with a blank role at segments
  34/39/41 and his full name occurs exactly once in the revision, in the role-free handoff "let me
  turn the call over to Nick Pointon" (seg 15); FANG's Chad McAllaster answers with a blank role at
  segment 92, referenced only by "I'll let Chad or Danny give the details" (seg 91). Corrected
  partition recorded in
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

# Blank role is not the signal — positive support is

`SCCO/2026Q2` and `COF/2026Q2` publish blank segment roles too, and are genuinely source-clean,
because their revisions carry replayable roster/title declarations binding their management
respondents to roles. The discriminating fact is never "is the segment role blank"; it is "does this
exact revision positively bind this person to a role". A method that refuses every blank role fails
SCCO and COF; a method that accepts every blank role fails ARQQ and FANG. Both failures look like a
passing implementation from one side only.

# Counting the right turns

The load-bearing count for `QNA_SOURCE_CLEAN` is answer turns **inside the Q&A window**, not total
speaking segments. Nick Pointon has 8 total speaking segments in ARQQ/2026Q2 but only 3 Q&A-window
answer turns (segments 34, 39, 41); the other 5 are prepared remarks (segments 16–20). An earlier
candidate record stated "eight answer turns", which conflates the two. The refusal does not depend
on the count — one unsupported accepted answer is sufficient — but a grading gate written against
the wrong number will not reproduce the frozen blocker set.

# Cross-cutting reading

The general form is the reason this is worth remembering outside E3: **a derived set stored as a
literal is not evidence of the rule that was supposed to derive it.** Any prereg that freezes both a
predicate and the population it selects should carry the derivation, not just the result, so a
later reader can replay the selection instead of trusting it.
