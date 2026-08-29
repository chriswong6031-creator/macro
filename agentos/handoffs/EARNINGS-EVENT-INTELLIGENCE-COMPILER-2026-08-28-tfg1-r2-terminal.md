---
workstream: WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
session: claude/tfg1-r3-gold-source-clean-correction-v3
model: opus
ended_because: complete
prs: [6591, 6602, 6606, 6608]
decisions:
  - DEC:E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN
discoveries:
  - DSC:E3FMT-ABSENCE-OF-ROLE-CONFLICT-IS-NOT-SOURCE-CLEAN
mission: >
  Close TFG-1 R2 as terminal on its accepted SECOND development-gold falsifier, and land the
  Sol-ratified respondent-role source-clean correction as records so the later deterministic R3
  implementation can be graded against true development gold. Records and research only: zero
  compiler or runtime behavior change, zero holdout spend.
state_before: >
  TFG-1 v1 was merged (#6555) and terminal on the FIRST, structural gold falsifier, which raised the
  ratified separator count from 110 to 113 and was ratified as
  DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS. The successor operation
  tfg1-r2-deterministic-transcript-format-hardening-20260827-v1 then hit a SECOND falsifier while
  implementing against the R2 gold: the respondent-role layer of that gold does not match source.
  Sol reviewed PR #6591 (review 5048161769, CHANGES_REQUESTED, 2026-08-28T05:27:16Z) and accepted
  both findings, then closed #6591 unmerged with its branch preserved as candidate evidence.
  Machine grading truth on main was still tfg1_development_boundary_identity_adjudication_r2.json,
  which asserts 2 management-role-conflict calls and 9 source-clean calls. Three successive
  correction carriers then closed unmerged WITHOUT landing the correction - #6602 at 8078d54b,
  #6606 at 1e068ce7 (post-STOP re-entry), and #6608 at bc811287 (RECEIVER_IDENTITY_UNRESOLVED,
  despite green exact-head CI) - so the corrected gold was absent from main at the start of this
  session and the R2 workstream record still described R2 as merely todo.
changed:
  - path: research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json
    what: >
      NEW superseding machine grading truth. Structural layer copied programmatically from the R2
      per_call block and asserted equal list-by-list for all 16 calls. Respondent-role layer
      corrected - conflicts 2 to 5, source-clean 9 to 7, refusal 7 to 9 - and per-call refusal
      reasons are now source_blockers SETS. Carries the full independent source re-verification
      receipt and the four corrections this carrier made to closed-candidate claims.
  - path: agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN.md
    what: >
      NEW decision ratifying the respondent-role correction and restating QNA_SOURCE_CLEAN as
      requiring POSITIVE replayable same-revision role support. Records the frozen per-call blocker
      sets and the closed-alias-table trap.
  - path: agentos/discoveries/DSC-E3FMT-ABSENCE-OF-ROLE-CONFLICT-IS-NOT-SOURCE-CLEAN.md
    what: >
      NEW discovery recording the second gold falsifier as a reusable landmine - absence of
      contradicting role evidence is not positive support - with the SCCO/COF discriminator that
      stops the naive "refuse every blank role" fix.
  - path: agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-28-tfg1-r2-terminal.md
    what: This handoff. Closes R2 as terminal and states what the R3 implementation inherits.
  - path: research/earnings_intelligence/e3/TFG1_R3_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-28.md
    what: >
      NEW sole packet for the successor implementation operation
      tfg1-r3-deterministic-transcript-format-hardening-20260828-v1, which remains NOT_BUILT.
  - path: agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md
    what: >
      Minimal update - E3-FMT-TFG-1-R2 wave moves to done/terminal on its accepted falsifier, a new
      E3-FMT-TFG-1-R3 wave records NOT_BUILT, next_action and the decisions list are updated to the
      corrected truth. No other wave, artifact or law touched.
verified:
  - claim: All 7 relevant development transcript bodies match the frozen selection receipt byte-for-byte.
    command: "python3 scratchpad verify3.py - re-fetch https://app.mastermind-x.com/data/tx/{TICKER}/{TXID}.json.gz, gzip.decompress, sha256, assert == body_sha256 in tfg0_transcript_format_development_corpus_selection.json"
    result: "7/7 hash_match=True for ARRY, CTRE, BANR, LTH, HTGC, ARQQ, FANG"
  - claim: The corrected partition equals the frozen truth exactly, set for set.
    command: "python3 scratchpad build.py - assertions on the generated summary block"
    result: "FROZEN TRUTH ASSERTIONS PASSED: 113 97 6 103 10 | conflicts 5 | clean 7 | refusal 9"
  - claim: The structural layer was carried over, not retyped, and is identical to ratified R2.
    command: "python3 scratchpad build.py - per-call assert n[k]==c[k] for all four index lists across 16 calls, plus assert F[k]==r2['summary'][k] for the five structural totals"
    result: "all 64 list comparisons and all 5 total comparisons passed"
  - claim: Every cited role-conflict respondent answers inside the ratified Q&A window, so the conflict is load-bearing for qa_exchange.v1.
    command: "python3 scratchpad gen_r3.py - assert qa_window_answer_turns >= 1 anchored to each call's first ratified structural handoff index from R2 per_call"
    result: "ARRY 2, CTRE 16, BANR 7, LTH 10, HTGC 1, ARQQ 3, FANG 1"
  - claim: Every declared title is present verbatim in the declaring segment it is cited to.
    command: "python3 scratchpad gen_r3.py - assert title in segs[declared_at_segment_index]['text'] for all five conflicts"
    result: "5/5 passed; ARRY seg 1, CTRE seg 2, BANR seg 1, LTH seg 1, HTGC seg 1"
  - claim: R2 and TFG-0 historical artifacts are preserved byte-unchanged.
    command: "git diff --stat origin/main HEAD -- research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r2.json research/earnings_intelligence/e3/tfg0_development_boundary_identity_adjudication.json agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS.md"
    result: "empty diff; blobs still 9017d327, 190cad1a, f48ea2a9"
  - claim: The holdout was never opened by this carrier.
    command: "grep of the fetch list in every verification script against the holdout ranks 17-24 (H, OMCL, MMS, HSHP, YUM, QMLS, MA, KYMR)"
    result: "holdout_revisions_touched 0; only the 16-revision development corpus opened at TFG-0 freeze was read; model_calls 0"
unverified: []
unresolved:
  - >
    The receiver binding for this carrier is not visible on the Slack carrier thread
    C0BSBM78V1N/1787944369.818849, which had zero replies when this session read it. This session
    proceeded under a Chairman override delivered out-of-band and disclosed that in its ACK. Sol
    must rule on the binding itself; three prior carriers died on receiver identity, not on content.
  - >
    E3-C remains GENERALIZATION_REFUSED_ON_SOURCE_FORMAT and incomplete. TFG completion is not E3-C
    completion; a fresh untouched-OOS acceptance wave E3-OOS2 is still required, and E3-P stays locked.
next_actions:
  - >
    Sol accepts or rejects this correction carrier. On acceptance the corrected R3 gold becomes the
    machine grading truth and the R2 operation key is spent.
  - >
    Only after that, commission ONE bounded worker on the successor implementation operation
    tfg1-r3-deterministic-transcript-format-hardening-20260828-v1 against its sole packet,
    research/earnings_intelligence/e3/TFG1_R3_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-28.md.
  - >
    That worker implements positive same-revision respondent role support, grades against
    113/97/6/103/10 with 7 source-clean and 9 refusal calls matching their exact blocker SETS, and
    freezes an implementation head BEFORE any holdout unseal is even proposed.
do_not_redo:
  - >
    Do not re-adjudicate the structural layer. 113 separators / 97 direct / 6 proxy / 103 supported /
    10 unresolved is twice-ratified and is carried over verbatim in the R3 record.
  - >
    Do not re-derive the respondent-role findings from scratch. All five conflicts and both
    missing-role-support findings were re-verified against source bytes this session with 7/7 hash
    matches; the receipt is in the R3 JSON under role_evidence_verification.
  - >
    Do not reopen, merge, mutate, rebase or cherry-pick wholesale from #6602, #6606 or #6608 or their
    branches. They are candidate evidence with no acceptance authority. Their six-file diffs may be
    read to avoid retyping, but three specific claims in them are WRONG and are corrected in the R3
    record: ARQQ answer turns (8 total speaking segments, only 3 in the Q&A window), LTH
    total_segments (126, not 143), FANG full-name occurrences (0, not 1), and HTGC tagged answer
    indices (segments 17-22 are prepared remarks, not Q&A answers).
  - >
    Do not widen the closed CEO/CFO/COO alias table to clear BANR, LTH or HTGC. Any widening broad
    enough re-admits CTRE and ARRY as clean and destroys two already-frozen conflicts.
  - >
    Do not "fix" the blank-role refusal by refusing every blank segment role. SCCO and COF publish
    blank roles and ARE source-clean because they declare the office in text.
  - >
    Do not open the holdout to adjudicate between the R2 and R3 definitions. It is single-use
    evidence and is sealed until an implementation head is frozen.
danger_areas:
  - >
    The alias table is the single most tempting wrong fix in this arc. It is closed at CEO/CFO/COO
    deliberately because CTRE tags its Chief Investment Officer as CFO.
  - >
    Q&A-window answer turns must be anchored to each call's first RATIFIED structural handoff index
    from the R2 per_call block. A re-derived operator-cue heuristic mis-classified prepared remarks
    as Q&A answers in three of seven calls during this session's verification and was discarded.
  - >
    The R2 adjudication, the TFG-0 adjudication and DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS
    are preserved byte-unchanged on purpose. Editing any of them to make the arc look tidier destroys
    the falsification record. This is also why the R3 DEC does not use the schema's supersedes field:
    that field requires writing superseded_by into the old record, which would break byte-preservation.
  - >
    This is a records-only correction. compiler_behavior_changed is false. Any diff touching engine/,
    tests, runtime, registry or production admission is out of scope for this carrier.
---

# What actually happened

TFG-1 R2 died the same way TFG-1 v1 did, one layer deeper. v1 implemented the frozen structural
separator law faithfully and discovered the frozen gold had omitted three real separators
(110 → 113). R2 implemented against that corrected gold and discovered the gold's **respondent-role**
layer was wrong in both directions at once.

Sol accepted both findings and closed PR #6591 unmerged rather than letting an implementation be
graded against a gold the source contradicts. This handoff and its sibling records land that
correction so the R3 implementation has something true to be graded against.

# The correction in one table

| | R2 (falsified) | R3 (ratified) |
|---|---|---|
| structural separators | 113 | **113 — unchanged** |
| direct / proxy / supported / unresolved | 97 / 6 / 103 / 10 | **unchanged** |
| management-role-conflict calls | 2 | **5** (+BANR, LTH, HTGC) |
| source-clean calls | 9 | **7** (−ARQQ, −FANG) |
| refusal calls | 7 | **9** |
| per-call refusal reason | one implicit string | **a SET** |

The structural half is untouched on purpose. Only the respondent-role half moved, and it moved in
the conservative direction: strictly fewer calls are trusted than R2 believed.

# Why ARQQ and FANG left the clean set

Both have a management respondent answering inside the Q&A window with a blank segment role and no
same-revision declaration binding them to any office. R2 called that clean because nothing
contradicted it. That is the falsified test. `QNA_SOURCE_CLEAN` requires **positive** replayable
same-revision support, so a respondent nobody's revision ever gives an office to cannot be published
with one.

The reason this is a real method requirement and not a blanket rule is SCCO and COF: they publish
blank segment roles too, and they stay clean, because their revisions declare the office in text.
Any implementation that refuses on blankness alone fails this gold just as surely as one that
accepts on blankness alone.

# Carrier note

Three consecutive correction carriers closed unmerged before this one, none for content reasons.
The six-file record set was never in dispute; the receiver binding was. That history is recorded in
`correction_carrier_lineage` inside the R3 adjudication JSON so a later session does not mistake a
closed candidate PR for a rejected finding.
