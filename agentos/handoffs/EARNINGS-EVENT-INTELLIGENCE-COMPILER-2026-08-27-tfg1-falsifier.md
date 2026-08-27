---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: claude/tfg1-deterministic-transcript-format-hardening
model: opus
ended_because: blocked
mission: >
  Implement the frozen TFG source-native separator/identity law inside the existing deterministic
  Q&A compiler, prove it against the frozen 16-call development adjudication, freeze the
  implementation head, then unseal and score the eight-slot unseen format holdout once, returning
  DRAFT/HOLD-FOR-SOL without widening production publication.
state_before: >
  TFG-0 was Sol-accepted and merged as a2dd436722dd0e6c6cb1e17bfa1c888c706c15d0. It measured the
  unchanged compiler at 0/16 on a pre-registered 16-revision development corpus, froze the
  source-conditioned separator/proxy/role law, and froze an eight-revision metadata-only holdout
  (ranks 17-24) that had never been opened. E3-C was open; E3-P locked.
prs:
  - 6555
discoveries:
  - DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES
changed:
  - path: research/earnings_intelligence/e3/TFG1_DEVELOPMENT_ADJUDICATION_FALSIFIER_2026-08-27.md
    what: >
      Records why TFG-1 stopped at the development gate: the frozen development adjudication
      undercounts structural separators by three, which moves MBLY/2026Q2 out of the source-clean
      set and makes the frozen 10/10 source-clean gate unsatisfiable without inventing an
      unlawful exclusion rule. States the three rulings Sol is asked to make.
  - path: research/earnings_intelligence/e3/tfg1_development_separator_falsifier_receipt.json
    what: >
      Machine receipt tfg1.development_separator_falsifier.v1 - per-call frozen vs detected
      separator indices for all 16 exact revisions, the three omitted separators with their
      Operator text, next speaker and first utterance, the corrected partition, and the explicit
      record that holdout_bodies_inspected is 0 and no compiler source changed.
  - path: agentos/discoveries/DSC-TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES.md
    what: >
      Records that mastermind.tx-index/v1 body_sha256 is a canonical-JSON re-serialization hash,
      so a raw-decompressed-bytes byte-replay gate reports a false SOURCE_REVISION_MISMATCH.
verified:
  - claim: "Dispatch base a2dd4367 is an ancestor of current origin/main; no E3/Q&A/identity law collided."
    command: "git merge-base --is-ancestor a2dd436722dd0e6c6cb1e17bfa1c888c706c15d0 origin/main; git log --oneline a2dd4367..origin/main -- research/earnings_intelligence engine/earnings agentos/decisions"
    result: "ancestor confirmed; 8 intervening commits; empty path-scoped log"
  - claim: "All 16 exact development revisions byte-replay to their frozen SHAs."
    command: "canonical replay: sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',',':')))"
    result: "16/16 (raw-decompressed-bytes convention gives 15/16, failing only COF/2026Q2)"
  - claim: "The frozen separator law, implemented faithfully, detects 113 structural separators against the frozen receipt's 110, with zero false negatives."
    command: "prototype separator predicate over the 16 exact revisions, diffed against tfg0_development_boundary_identity_adjudication.json per_call"
    result: "recall 110/110, false negatives 0, residual detections 3 (MBLY #21, ARRY #31, KREF #15)"
  - claim: "Direct-questioner name extraction is exact on every frozen direct handoff."
    command: "compare extracted Operator-named person to the immediate next non-housekeeping speaker across the frozen direct_next_speaker_match_indices"
    result: "95/95 exact, 0 failures"
  - claim: "The three omissions are not a detector artifact: the same construction is counted in 13 of 16 calls."
    command: "inspect the first frozen separator of every call (OCSL #29, GEF #25, ARQQ #22, TRVI #12, CTRE #17, LTH #10, UPBD #32, SCCO #53, AGM #30, BANR #20, FANG #4, HTGC #33, COF #20)"
    result: "all 13 are the same combined Q&A-opener-plus-first-question segment and all 13 are counted"
  - claim: "Probe truncation does not explain the omissions."
    command: "measure normalized length and handoff-clause offset of the three omitted segments against the TFG-0 probe clip of 650 chars"
    result: "lengths 463/421/482, clause offsets 372/351/412 - all inside the clip; counted segments run longer (LTH #10 = 557)"
  - claim: "No structural separator is missed anywhere in the corpus."
    command: "sweep every housekeeping segment the predicate rejects and inspect its next non-housekeeping source turn"
    result: "13 blank-role followers, all IR or management at call open/close; no analyst handoff unaccounted for"
  - claim: "MBLY/2026Q2 #21 has an unresolved questioner under the frozen proxy law."
    command: "read MBLY/2026Q2 segments 21-22 in the exact held revision"
    result: "Operator names Joshua Buchalter; next structured speaker is placeholder 'Speaker 4' whose first utterance is 'This is Lanny on for Josh' - placeholder plus first-name-only, the frozen unresolved class"
  - claim: "agentos records validate."
    command: "python3 scripts/agentos.py validate"
    result: "863 records, 0 errors, 43 pre-existing warnings"
unverified:
  - claim: "The corrected partition figures (113/97/6/103/10, nine source-clean calls) are the values Sol will ratify."
    what_would_verify: "a Sol amendment to the frozen development adjudication accepting or revising them"
  - claim: "The prototype separator predicate is production-quality for the compiler path."
    what_would_verify: "it was never landed in engine/ - it exists only as measurement evidence for the falsifier; a future wave must implement it under RED-first TDD against the amended gold"
unresolved:
  - "Whether the frozen development adjudication is amended to 113 separators and a nine-call source-clean set."
  - "Whether MBLY/2026Q2 is reclassified source-conflicted with an expected unresolved-questioner failure at #21."
  - "Whether TFG-1 re-runs as a fresh implementation wave against the amended gold."
next_actions:
  - "Sol rules on the three questions in TFG1_DEVELOPMENT_ADJUDICATION_FALSIFIER_2026-08-27.md section 7."
  - "If amended, re-commission TFG-1 implementation against the corrected gold with the holdout still sealed."
  - "Do not open the eight holdout revisions until an implementation head is frozen against a ratified gold."
do_not_redo:
  - "Do not re-derive the separator grammar from scratch: the predicate that achieves 110/110 recall with zero false negatives and exact direct-name extraction is described in the falsifier record and its receipt."
  - "Do not byte-replay transcript revisions with sha256 of the raw decompressed body - it reports a false SOURCE_REVISION_MISMATCH on COF/2026Q2. Use the canonical-JSON convention (DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES)."
  - "Do not re-test the probe-truncation or deliberate-first-handoff-convention explanations for the three omissions; both are measured and falsified."
  - "Do not treat COF/2026Q2 as a moved or corrected revision."
  - "Do not invent a first-handoff exemption, edit distance, nickname map or initials expansion to make MBLY/2026Q2 pass - that is the rescue the dispatch forbids."
danger_areas:
  - "The eight-slot holdout is single-use and explicitly non-replaceable. Opening it against an unratified development gold destroys the only unseen format evidence TFG owns, with no lawful substitute."
  - "Excluding a real question handoff is not neutral: segments before the first admitted boundary fall outside every exchange window, so the first analyst exchange of that call is silently discarded."
  - "engine/company_intelligence/qa_exchange.py pins RESPONDENT_KEYS to exactly four keys and Terminal mirrors that shape, so any roster identity_evidence variant must be proven backward-safe before publication."
---

# TFG-1 stopped at the development gate

The frozen TFG separator law was implemented faithfully and measured against the frozen 16-call
development adjudication. It recovers every one of the 110 adjudicated handoffs with zero false
negatives and extracts the questioner name exactly on all 95 frozen direct matches — and it finds
three more genuine structural separators that the frozen receipt omits.

The three are each the segment where the Operator both opens the Q&A session and names the first
questioner: `MBLY/2026Q2` #21, `ARRY/2026Q2` #31, `KREF/2026Q2` #15. Thirteen of the sixteen calls
contain that identical construction and the frozen receipt counts all thirteen, so this is an
inconsistency in the gold rather than a detector artifact. Probe truncation and a deliberate
first-handoff convention were both tested and falsified.

Correcting the omission moves `MBLY/2026Q2` out of the source-clean set, because its first handoff
resolves to a structured placeholder with first-name-only self-identification — the frozen
unresolved class. The frozen development gate demands non-empty reconstruction on all ten
source-clean calls, so that gate is now unsatisfiable without inventing an exclusion rule the
dispatch explicitly forbids. Under the dispatch stop conditions the wave returns the falsifier
rather than rescuing it.

No compiler source was changed, production admission remains AAPL-only, and the eight-slot holdout
remains sealed and unopened. Sol's ruling is requested on the three questions in section 7 of
`research/earnings_intelligence/e3/TFG1_DEVELOPMENT_ADJUDICATION_FALSIFIER_2026-08-27.md`.
