---
key: E3FMT-ABSENCE-OF-ROLE-CONFLICT-IS-NOT-SOURCE-CLEAN
claim: >
  A transcript revision can name a management respondent and still bind them to NO office, and
  the TFG development gold twice mistook that silence for cleanliness. In the 16-revision E3-FMT
  development corpus, ARQQ/2026Q2 (Nick Pointon, 3 Q&A-window answer turns) and FANG/2026Q2
  (Chad McAllaster, 1 Q&A-window answer turn) each answer with a BLANK segment role and no
  same-revision roster or title declaration; FANG's full name never appears in any segment TEXT at
  all, only in speaker metadata. R2 graded both source-clean because no CONFLICTING role evidence
  existed, so the R2 gold would have trained the compiler to mint qa_exchange.v1 respondents with
  zero replayable role support. The correct test is POSITIVE same-revision support, which drops the
  clean set 9 -> 7 and raises the refusal set 7 -> 9. The same blind spot ran the other way: three
  further calls carry explicit incompatible evidence R2 missed (BANR Jill Rice declared "our Chief
  Credit Officer" but tagged CFO; LTH Erik Weaver declared "Executive Vice President and CFO" but
  tagged CEO; HTGC Seth Meyer declared "President" but tagged CEO), taking conflicts 2 -> 5.
  Blankness itself is NOT the discriminator: SCCO/2026Q2 and COF/2026Q2 also publish blank segment
  roles and ARE clean, because their revisions declare the office in text ("Andrew Young, Capital
  One's Chief Financial Officer").
falsifier: >
  Re-fetch the seven revisions from https://app.mastermind-x.com/data/tx/{TICKER}/{TXID}.json.gz,
  confirm each decompressed body sha256 against tfg0_transcript_format_development_corpus_selection.json,
  and search the segment array for a same-revision role or title declaration binding Nick Pointon
  (ARQQ) or Chad McAllaster (FANG) to an office. Finding one refutes D2 and restores those calls to
  the clean set. Symmetrically, finding that Jill Rice / Erik Weaver / Seth Meyer are NOT declared
  with the offices above, or that those declarations reconcile with the tagged segment role through
  the closed CEO/CFO/COO alias table, refutes D1.
so_what: >
  Never grade a respondent-identity contract on "no contradiction found". Any source-conditioned
  cleanliness test in this arc must require positive, replayable, same-revision evidence, and must
  separate blank-role-with-declaration (SCCO, COF - clean) from blank-role-without-declaration
  (ARQQ, FANG - refuse). A parser that refuses every blank segment role is exactly as wrong as one
  that accepts every blank segment role, so "just require a non-empty role" is not the fix. Record
  per-call refusal reasons as SETS: CTRE, LTH, BANR and HTGC each carry BOTH unresolved_questioner
  and management_role_conflict, and a scalar first-failure reason makes the gate depend on
  evaluation order rather than source truth. Expect the narrowed definition to LOWER the holdout
  clean count; an INSUFFICIENT_HOLDOUT_POWER stop is a legitimate outcome and must not be rescued
  by reverting to the falsified definition.
kind: data
verified_at: 2026-08-28
verified_by: >
  Sol review #5048161769 on PR #6591 head 77fd9411c9cfb799b245c8138d2f1a40052d3b8d
  (CHANGES_REQUESTED, 2026-08-28T05:27:16Z) accepted falsifiers D1 and D2.
  Independently re-verified against source bytes by correction carrier
  tfg1-r3-gold-source-clean-correction-recovery-20260828-v3: all 7 relevant development bodies
  re-fetched and sha256-matched 7/7 against the frozen selection receipt; every declared title
  asserted present in its cited declaring segment; every respondent asserted to resolve to exactly
  one tagged segment role and to answer at least once at or after that call's first RATIFIED
  structural handoff index. Measured: ARQQ Nick Pointon role '' , segments 16-20 prepared / 34,39,41
  Q&A, full-name occurrences 1; FANG Chad McAllaster role '', segment 92 Q&A, full-name occurrences
  0; BANR Jill Rice tagged CFO declared seg 1; LTH Erik Weaver tagged CEO declared seg 1;
  HTGC Seth Meyer tagged CEO declared seg 1; CTRE James Callister tagged CFO declared seg 2;
  ARRY Neil Manning tagged CFO declared seg 1. holdout_revisions_touched 0; model_calls 0.
  Canonical record: research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json
scope: [macro]
confidence: verified
---

## Detail

This is the SECOND falsifier of the same development gold, and the two have the same shape: the
frozen gold asserted a partition that the source bytes do not support, and a faithful implementation
found it. The first (TFG-1 v1) was structural — three omitted combined Q&A-opener-plus-first-question
separators, 110 → 113. This one is the respondent-role layer, and the structural layer is carried
over from R2 completely unchanged: **113 separators / 97 direct / 6 proxy / 103 supported /
10 unresolved**.

The load-bearing asymmetry is that the two corrections move in opposite directions but both make the
gate STRICTER:

- **D1 (conflicts 2 → 5)** costs nothing in partition terms. BANR, LTH and HTGC were already
  non-clean for `unresolved_questioner`, so D1 changes only their frozen refusal reason SET. It
  matters because an implementation graded against the R2 reason would refuse them for the right
  outcome via the wrong mechanism, and would therefore pass while its conflict detector was blind.
- **D2 (clean 9 → 7)** does move the partition. ARQQ and FANG leave the clean set entirely.

The trap for a future implementer is the alias table. Every one of the three new conflicts looks
like it could be absorbed by "just add more role synonyms" — Chief Credit Officer, President,
Executive Vice President. It cannot: the table is deliberately closed at CEO/CFO/COO precisely
because CTRE tags its **Chief Investment Officer** as CFO. Any widening broad enough to clear BANR,
LTH and HTGC re-admits CTRE and ARRY as clean and silently destroys two already-frozen conflicts.

The FANG case is the cleanest statement of the principle. Chad McAllaster answers exactly once in
the Q&A window (segment 92) and his full name appears in the transcript text **zero** times — the
only in-text reference is first-name-only, "I'll let Chad or Danny give the details" at segment 91.
There is nothing in that revision to replay. Under the R2 definition he was clean.
