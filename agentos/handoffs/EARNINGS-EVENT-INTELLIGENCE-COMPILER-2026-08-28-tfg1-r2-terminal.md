---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: claude/tfg1-r3-gold-source-clean-correction-v2
model: opus
ended_because: complete
mission: >
  Land the truthful records/source-law correction produced by TFG-1 R2's second development-gold
  falsifier — without changing compiler behavior and without spending the sealed holdout — so a fresh
  R3 implementation wave can be graded against correct source truth. Records/research only.
state_before: >
  TFG-1 R2 (operation tfg1-r2-deterministic-transcript-format-hardening-20260827-v1) recovered
  113/113 structural separators against the ratified R2 gold, then found that gold's respondent-role
  layer contradicted the frozen TFG-0 identity-evidence amendment on two counts. D1: the gold
  recorded 2 explicit management-role-conflict calls when the same revisions carry 5 — BANR declares
  Jill Rice "our Chief Credit Officer" while tagging her CFO, LTH declares Erik Weaver "Executive
  Vice President and CFO" while tagging him CEO, and HTGC declares Seth Meyer "President" while
  tagging him CEO, each alongside the already-declared ARRY and CTRE. D2: the gold marked ARQQ and
  FANG source-clean although Nick Pointon (ARQQ) and Chad McAllaster (FANG) answer inside the Q&A
  window with blank segment roles and no same-revision title declaration, so the gold was treating
  absence of conflict as positive support. Sol review #5048161769 (CHANGES_REQUESTED,
  2026-08-28T05:27:16Z) accepted both, ruled the operation terminal
  STOPPED_AT_DEVELOPMENT_GATE — SECOND GOLD FALSIFIER, and closed PR #6591 UNMERGED at exact head
  77fd9411c9cfb799b245c8138d2f1a40052d3b8d. The R2 carrier was left unmutated, no implementation head
  was ever frozen, and holdout_bodies_inspected stayed 0. Sol's ruling required a new records-only
  operation/carrier to amend the durable gold before any successor implementation is commissioned.
  A first correction carrier (tfg1-r3-gold-source-clean-correction-20260828-v1, direct-targeted to
  Claude6) went terminal UNCLAIMED_RECEIVER_UNAVAILABLE with no receiver ACK/START/branch/PR/effect;
  its candidate records PR #6602 was closed at head 8078d54ba89217b26559973b9149cc3fa0a092b7 and
  retained as candidate evidence only. This handoff belongs to the recovery carrier
  tfg1-r3-gold-source-clean-correction-recovery-20260828-v2.
prs:
  - 6591
decisions:
  - DEC:E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN
  - DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS
  - DEC:E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT
discoveries:
  - DSC:E3FMT-ABSENCE-OF-ROLE-CONFLICT-IS-NOT-SOURCE-CLEAN
  - DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES
changed:
  - path: research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json
    what: >
      New superseding machine grading truth. Carries every R2 structural index over verbatim
      (113 separators / 97 direct / 6 proxy / 103 supported / 10 unresolved) and corrects only the
      respondent-role layer: 5 role-conflict calls, 7 source-clean calls, 9 non-clean calls. Adds a
      per-call source_blockers SET, a blocker vocabulary bound to the frozen runtime refusal codes,
      an explicit QNA_SOURCE_CLEAN definition requiring positive same-revision role support, a
      corrections_from_r2 block recording D1/D2/D3, per-call named role evidence, and a
      role_evidence_verification block. Records holdout_bodies_inspected 0, model_calls 0,
      compiler_behavior_changed false.
  - path: agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN.md
    what: >
      Ratifies the respondent-role correction as a partial gold amendment scoped to the respondent
      layer only. Names the 5 conflict calls with their verified declared-title-vs-tagged-role
      evidence, the 7 clean calls, the 9 blocker sets, and the seven rejected alternatives including
      publishing an empty/generic role and relaxing conflict detection. States that the R2 decision
      and adjudication are preserved byte-unchanged with their blob SHAs.
  - path: agentos/discoveries/DSC-E3FMT-ABSENCE-OF-ROLE-CONFLICT-IS-NOT-SOURCE-CLEAN.md
    what: >
      Records the second gold falsifier and its general form — a derived set stored as a literal is
      not evidence of the rule that was supposed to derive it, so a cleanliness predicate must be
      written as positive support AND no contradiction, never as no-contradiction alone.
  - path: research/earnings_intelligence/e3/TFG1_R3_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-28.md
    what: >
      Sole active successor implementation packet under new operation key
      tfg1-r3-deterministic-transcript-format-hardening-20260828-v1. Corrected 113/103/10/7/9 gates,
      the frozen blocker-set table, named role-conflict evidence with a warning not to hard-code the
      declaring segment index or declaring speaker role, the SCCO-COF versus ARQQ-FANG discriminator
      that any compliant method must separate, PR #6591 and #6602 candidate-reuse-without-mutation
      law, the R2 corpus facts already paid for, and unchanged single-use holdout law under the
      corrected clean definition.
  - path: agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md
    what: >
      Minimal state update. Wave E3-FMT-TFG-1-R2 moves todo to done/TERMINAL with pr 6591; new wave
      E3-FMT-TFG-1-R3 added as todo/NOT_BUILT; next_action rewritten to R2 terminal / R3 NOT_BUILT;
      the R3 decision and discovery registered; six new artifacts listed. Three do_not_redo entries
      that carried the now-falsified 9-clean/7-refusal partition, the spent operation keys and the
      R2-scoped holdout gate were corrected, and five new entries added covering positive role
      support, blocker sets, the closed alias table, the verified role evidence, and the do-not-mutate
      law for PR #6591 and #6602.
  - path: agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-28-tfg1-r2-terminal.md
    what: >
      This continuation records R2's terminal state and the landed correction. The prior
      EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-27-tfg1-r2-ready.md handoff remains historical
      evidence of the R2 commission and is not edited.
verified:
  - claim: "The ratified R3 partition is mechanically consistent with the R2 gold's own per_call block, so no threshold was re-adjudicated."
    command: >
      python3 scratchpad/gen_r3.py — loads the landed R2 adjudication, rebuilds each per_call row, and
      asserts sums of true_question_handoff_indices, direct_next_speaker_match_indices,
      explicit_full_name_proxy_indices and unresolved_questioner_indices, the identity
      handoffs == direct + proxy + unresolved, and that the clean/refusal/conflict sets equal the
      frozen dispatch sets.
    result: >
      "ASSERTIONS PASS: 113 handoffs = 97 direct + 6 proxy + 10 unresolved; 7 clean + 9 refusal = 16;
      5 conflict". Supported = 97 + 6 = 103.
  - claim: "Every structural index in the R3 adjudication is byte-identical to the R2 adjudication, because it was copied rather than retyped."
    command: >
      The same generator copies the four index lists directly from the loaded R2 per_call rows, then
      asserts equality pairwise for all 16 calls before writing; a mismatch raises AssertionError and
      emits no file.
    result: "All 16 calls matched on all four index lists. Only respondent-role fields differ."
  - claim: "Every named respondent-role fact in these records was independently verified against source bytes, not carried on trust from the closed candidate PR."
    command: >
      Refetched BANR/LTH/HTGC/CTRE/ARQQ/FANG/ARRY 2026Q2 from
      https://app.mastermind-x.com/data/tx/{TICKER}/2026Q2.json.gz, re-hashed each body against the
      frozen body_sha256 in tfg0_transcript_format_development_corpus_selection.json, and read the
      declaring segment and tagged answer segments directly.
    result: >
      7/7 bodies matched the frozen body_sha256 on decompressed bytes. All 7 claims CONFIRMED:
      ARRY/Neil Manning "our President and COO" (seg 1) tagged CFO; CTRE/James Callister "Chief
      Investment Officer" (seg 2) tagged CFO; BANR/Jill Rice "our Chief Credit Officer" (seg 1)
      tagged CFO; LTH/Erik Weaver "Executive Vice President and CFO" (seg 1) tagged CEO; HTGC/Seth
      Meyer "President" (seg 1) tagged CEO; ARQQ/Nick Pointon blank role at segs 34/39/41 with his
      full name occurring exactly once in the revision, in "let me turn the call over to Nick
      Pointon" (seg 15); FANG/Chad McAllaster blank role at seg 92, referenced only by "I'll let Chad
      or Danny give the details" (seg 91). Holdout revisions touched: 0.
  - claim: "The closed #6602 candidate contained a factual error about ARQQ that these records correct."
    command: >
      Compared the candidate's "Nick Pointon ... eight answer turns" against the fetched ARQQ/2026Q2
      body, counting his speaking segments inside and outside the Q&A window.
    result: >
      Nick Pointon has 8 TOTAL speaking segments but only 3 Q&A-window answer turns (34, 39, 41); the
      other 5 (16-20) are prepared remarks. The landed records state 3 Q&A-window answer turns and
      explain the distinction; the refusal itself is unaffected because one unsupported accepted
      answer is sufficient.
  - claim: "The R2 and TFG-0 historical artifacts are preserved byte-unchanged."
    command: >
      git diff origin/main -- <path> | wc -l for tfg1_development_boundary_identity_adjudication_r2.json,
      tfg0_development_boundary_identity_adjudication.json,
      DEC-E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS.md,
      TFG1_R2_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-27.md,
      TFG1_DEVELOPMENT_ADJUDICATION_FALSIFIER_2026-08-27.md,
      tfg1_development_separator_falsifier_receipt.json,
      tfg1_transcript_format_holdout_selection.json,
      TFG1_TRANSCRIPT_FORMAT_HOLDOUT_PREREG_2026-08-27.md and
      EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-27-tfg1-r2-ready.md.
    result: "0 diff lines for all nine paths."
  - claim: "The holdout was not opened, replaced, reranked or otherwise spent by this operation."
    command: >
      Read holdout_bodies_inspected in the new R3 adjudication; diffed
      tfg1_transcript_format_holdout_selection.json and TFG1_TRANSCRIPT_FORMAT_HOLDOUT_PREREG_2026-08-27.md
      against origin/main; and restricted the role-evidence refetch to an explicit seven-ticker list
      drawn only from the already-open 16-revision development corpus.
    result: >
      holdout_bodies_inspected is 0; both holdout files show a 0-line diff. Ranks 17-24 remain sealed
      and no holdout body, role vocabulary, Operator text or speaker metadata was read.
  - claim: "The SCCO/COF-versus-ARQQ/FANG discriminator holds against source: SCCO and COF publish blank management roles yet DO carry same-revision roster/title declarations, so they are genuinely source-clean."
    command: >
      Refetched SCCO/2026Q2 and COF/2026Q2 from https://app.mastermind-x.com/data/tx, enumerated every
      management respondent answering inside the Q&A window (excluding Operator and analysts), and
      searched each revision for a participant/title declaration binding that person to a role.
    result: >
      Both revisions carry role vocabulary {"Operator", ""} only — every management respondent has a
      BLANK segment role, exactly like ARQQ and FANG. But every one of them is positively bound by an
      in-revision declaration. SCCO: Raúl Jacob Ruisánchez (answers segs 55-127), declared at seg 0 by
      the Operator as "Mr. Raúl Jacob, Vice President of Finance, Treasurer, and CFO". COF: Richard
      Fairbank and Andrew Young, declared at seg 1 by Jeff Norris as "Mr. Richard Fairbank, Capital
      One's Chairman and Chief Executive Officer, and Mr. Andrew Young, Capital One's Chief Financial
      Officer", plus Jeff Norris himself declared at seg 0 as "Jeff Norris, Senior Vice President of
      Finance". 4/4 management respondents across the two calls have positive same-revision support,
      confirming the frozen clean status of both and confirming that blankness alone is not the signal.
  - claim: "Neither SCCO/2026Q2 nor COF/2026Q2 has drifted from the frozen development-corpus revision."
    command: >
      sha256 under BOTH conventions against tfg0_transcript_format_development_corpus_selection.json:
      raw decompressed bytes, and the canonical re-serialization
      json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',',':')) named by
      DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES.
    result: >
      Canonical convention: SCCO 9c657f21… MATCH, COF e9402d4e… MATCH — neither revision moved.
      The raw-bytes convention false-fails COF exactly as that DSC predicts, returning
      7951bd19b13b4879526e6756aab882016348fcc9838f36f3c4e3ee8b68fa92c6, which is the precise value the
      DSC records as its own falsifier. Reproducing that raw hash byte-for-byte (identical across 3
      independent fetches, same ETag) is therefore POSITIVE confirmation that COF is unmoved, not
      evidence of drift. A first pass that hashed only raw bytes read this as possible revision drift
      warranting escalation; the canonical check closes it with no escalation required.
  - claim: "The correction changed no compiler behavior and no runtime surface."
    command: "git status --porcelain against origin/main"
    result: >
      Five paths, all under agentos/ or research/earnings_intelligence/e3/: the R3 adjudication, the
      R3 DEC, the R3 DSC, the R3 implementation packet, and the modified workstream record — plus this
      handoff. No engine/, tests/, scripts/, templates/, site/, data/, Terminal or workflow file is
      touched.
  - claim: "PR #6591 is closed unmerged at the exact head Sol reviewed, and neither it nor #6602 was mutated."
    command: "gh pr view 6591 / 6602 --json number,state,headRefName,headRefOid,mergedAt,files"
    result: >
      #6591 state CLOSED, mergedAt null, headRefOid 77fd9411c9cfb799b245c8138d2f1a40052d3b8d on branch
      claude/tfg1-r2-transcript-format-hardening. #6602 state CLOSED, mergedAt null, headRefOid
      8078d54ba89217b26559973b9149cc3fa0a092b7 on branch claude/tfg1-r3-gold-source-clean-correction.
      This operation performed no write of any kind against either PR or branch; it branched a
      distinct name (claude/tfg1-r3-gold-source-clean-correction-v2) precisely because #6602's branch
      name already existed on the remote.
  - claim: "Sol review #5048161769 accepts D1 and D2 and rules the R2 operation terminal."
    command: >
      gh api repos/mastermindx-market-intelligence/macro/pulls/6591/reviews, selecting id 5048161769.
    result: >
      state CHANGES_REQUESTED, user mastermindx-3, submitted_at 2026-08-28T05:27:16Z. Body accepts D1
      (conflict count 5) and D2 (source-clean set 7), requires blocker sets rather than one
      order-dependent reason, declares terminal STOP for the R2 operation, and requires a new
      records-only operation/carrier before any successor implementation is commissioned.
  - claim: "AgentOS records validate cleanly on the rebased head, and this change introduces no error or warning of its own."
    command: >
      python3 scripts/agentos.py validate — run three times: on a clean tree at the original base
      5542999e, on a PRISTINE origin/main extracted to a temp dir via `git archive origin/main agentos
      scripts`, and on this branch after rebasing onto current origin/main bca7221a.
    result: >
      At the original base 5542999e: 905 records — 7 errors, all owned by
      agentos/handoffs/BREATHING-PLATFORM-2026-08-28-completion-commission.md and none mine. Those
      errors were then repaired ON MAIN by #6605 (commit bca7221a,
      "heal(agentos): schema-normalize the breathing completion-commission handoff"), so the
      inheritance is now historical rather than live. Pristine origin/main at bca7221a: 0 errors.
      This branch rebased onto bca7221a: 908 records (52 workstreams, 264 decisions, 231 discoveries,
      361 handoffs) — 0 errors, 53 warnings, exit 0. The +3 records are exactly this change's DEC,
      DSC and handoff, and no error or warning names any file it touches.
unverified:
  - claim: "The R3 gold's respondent-role layer is itself free of a third falsifier."
    what_would_verify: >
      The R3 implementation wave measuring same-revision respondent role evidence across all 16
      development revisions and reporting a blocker set per call that matches the frozen sets exactly.
      This carrier verified the named evidence for the 7 respondent-layer calls it asserts, but did
      not re-measure the 9 calls it carries over unchanged from R2, because that is implementation work.
  - claim: "The eight-slot holdout remains adequately powered under the narrowed clean definition."
    what_would_verify: >
      Only the R3 wave, after its development gates are green and its implementation head is frozen,
      may open the eight bodies and source-adjudicate them. The corrected definition is strictly
      narrower than R2's, so the clean count can only fall and an INSUFFICIENT_HOLDOUT_POWER stop is a
      live possibility.
  - claim: "PR #6591's implementation commits are reusable for R3."
    what_would_verify: >
      An R3 worker reading that diff as a candidate and re-deriving each behavior under its own
      RED-first discriminators. Sol explicitly declined to accept those commits as implementation truth.
unresolved:
  - >
    R3 implementation performance is unknown. The holdout source-clean count and compiler result are
    intentionally unknown because the holdout remains sealed at holdout_bodies_inspected 0.
  - >
    Whether the narrowed clean definition leaves the holdout powered at 6/8 or better cannot be known
    without spending it, and it may not be spent to find out.
  - >
    Parent E3-C remains incomplete even if TFG-1 R3 later succeeds; a fresh untouched-production-OOS
    operation (E3-OOS2) is still required for closure, and E3-P stays locked behind it.
next_actions:
  - >
    Sol reviews this records-only correction carrier at its exact head and accepts or rejects the
    encoded R3 source truth. The carrier is DRAFT / HOLD-FOR-SOL and must not be merged by any
    sweeper, label or session before that acceptance.
  - >
    After the correction lands, commission exactly one bounded frontier coding worker on
    research/earnings_intelligence/e3/TFG1_R3_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-28.md
    under new operation key tfg1-r3-deterministic-transcript-format-hardening-20260828-v1.
  - >
    If that worker is handed off via Slack, the initial envelope must require the exact ACK before
    work, a full-thread read, and no execution before both steps; Slack ACK remains transport evidence only.
  - >
    Do not start fresh E3-OOS2 or E3-P unless and until Sol independently accepts a successful R3 return.
do_not_redo:
  - "Do not re-adjudicate the R3 thresholds. 113/97/6/103/10, 5 conflict calls, 7 source-clean and 9 non-clean with their exact blocker sets are Sol-ratified in review #5048161769 and encoded in the R3 adjudication."
  - "Do not edit the R2 or TFG-0 adjudications or DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS to conceal either falsifier. Both are preserved byte-unchanged as falsified experimental evidence, with blob SHAs recorded in the R3 adjudication."
  - "Do not reuse operation keys tfg1-deterministic-transcript-format-hardening-20260827-v1, tfg1-r2-deterministic-transcript-format-hardening-20260827-v1 or tfg1-r3-gold-source-clean-correction-20260828-v1. All three are spent."
  - "Do not mutate, reopen, merge, reset, force-push or wholesale cherry-pick PR #6591 or PR #6602 or their branches."
  - "Do not re-verify the five role conflicts or the two missing-role-support findings against source. All seven were refetched, SHA-matched and confirmed by this carrier; the named evidence is in the R3 adjudication per_call rows and the DEC evidence table."
  - "Do not repeat the ARQQ answer-turn count error. Nick Pointon has 8 total speaking segments but 3 Q&A-window answer turns (34, 39, 41); segments 16-20 are prepared remarks."
  - "Do not re-derive the SCCO/COF discriminator. Measured and spent: both revisions carry role vocabulary {Operator, ''} only, and all four management respondents are bound by same-revision declarations — SCCO/Raúl Jacob Ruisánchez (seg 0), COF/Richard Fairbank and Andrew Young (seg 1), COF/Jeff Norris (seg 0)."
  - "Do not escalate COF/2026Q2 as revision drift on a raw-bytes hash. Raw decompressed hashing returns 7951bd19… and false-fails by design; the canonical re-serialization returns e9402d4e… and matches. DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES records the raw value as its own falsifier, so seeing 7951bd19… proves the revision is unmoved."
  - "Do not treat absence of role conflict as source-clean, and do not rescue ARQQ or FANG by publishing an empty or generic respondent role, or by filling the role from an external roster, biography or model inference."
  - "Do not relax conflict detection to clear BANR, LTH or HTGC; the same relaxation stops detecting the already-ratified ARRY and CTRE conflicts."
  - "Do not widen the closed CEO/CFO/COO alias table. CIO is excluded on purpose because CTRE tags its Chief Investment Officer as CFO."
  - "Do not collapse a call's blocker set into one order-dependent first-failure reason."
  - "Do not open, replace, skip or rerank the eight holdout bodies before an R3 implementation-head freeze, and do not revert to the falsified absence-of-conflict definition to reach holdout power."
  - "Do not inspect CAT/BAC/SNOW or use GOOGL as clean OOS evidence."
  - "Do not widen production AAPL-only revision admission, register Alphabet, create another Q&A/person/transcript/model/control plane, or start E3-P."
danger_areas:
  - >
    A gold can be internally coherent and still wrong. The R2 gold's totals reconciled exactly and were
    verified twice, yet its clean set contradicted the very law it encoded, because the set was stored
    as a literal list of pairs rather than derived from the predicate. Re-derive any frozen set from
    its predicate before ratifying it.
  - >
    The two falsifiers failed differently and one did not surface the other. The first was an omission
    of real separators, detectable by counting. The second is definitional: ARQQ and FANG have no
    missing structure at all and look maximally clean from the questioner side, failing only on the
    respondent side against a rule the gold never re-derived.
  - >
    SCCO and COF are the trap in the other direction. They also publish blank segment roles yet are
    genuinely clean, because their revisions carry replayable roster/title declarations. Verified
    against source: both revisions expose role vocabulary {"Operator", ""} only, so EVERY management
    respondent there has a blank role exactly like ARQQ and FANG, and all four are nonetheless bound
    by an in-revision declaration. A method that refuses every blank role is as wrong as one that
    accepts every blank role.
  - >
    Hashing the RAW decompressed body instead of the canonical re-serialization false-fails
    COF/2026Q2 and reads exactly like a corrected/republished transcript. It happened during this
    carrier: a first pass hashed raw bytes, got 7951bd19…, and proposed escalating COF as possible
    revision drift. The canonical convention from DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES
    returns e9402d4e… and matches. Because that DSC records the raw value as its own falsifier,
    reproducing 7951bd19… is positive proof the revision is UNMOVED. Always re-check with the
    canonical convention before declaring any revision moved — the failure is loud, plausible, and
    lands on exactly one slot in sixteen.
  - >
    The role declaration is not structurally uniform. CTRE declares at segment 2 rather than 1, and
    the declaring speaker is variously IR, the CEO, or a blank-role speaker. Hard-coding the declaring
    segment index or the declaring speaker's role will pass some of the five conflicts and miss others.
  - >
    A candidate record from a dead carrier is not evidence. PR #6602's six-file diff was substantively
    correct but carried a wrong operation key and a wrong ARQQ answer-turn count. Inspect such a diff
    to avoid retyping, then re-verify every value independently.
  - >
    The narrowed clean definition can only lower the holdout clean count, so an INSUFFICIENT_HOLDOUT_POWER
    stop is a foreseeable and legitimate outcome. It must not be rescued by widening the definition back,
    because the holdout is single-use and non-replaceable.
  - >
    A TFG-1 R3 pass would be method-hardening evidence only. It is not second-issuer production proof
    and cannot close E3-C or unlock E3-P.
---

# TFG-1 R2 terminal — second gold falsifier accepted, R3 source truth corrected

Sol accepted the R2 development-gold falsifier and terminated the R2 operation. This records-only
operation, `tfg1-r3-gold-source-clean-correction-recovery-20260828-v2`, encodes the corrected source
truth so a fresh implementation wave can be graded against it. No compiler behavior changed and the
holdout was not touched.

**Current capability state:** TFG-0 `SPEC_ONLY`; TFG-1 v1 `STOPPED_AT_DEVELOPMENT_GATE` on the first
(structural) gold falsifier; TFG-1 R2 `STOPPED_AT_DEVELOPMENT_GATE — SECOND GOLD FALSIFIER` on the
respondent-role layer; TFG-1 R3 `NOT_BUILT`; E3-C in progress; E3-P locked.

## What the correction changes

| Quantity | R2 gold | R3 gold |
|---|---|---|
| structural separators | 113 | 113 |
| direct questioners | 97 | 97 |
| explicit full-name proxies | 6 | 6 |
| source-supported questioners | 103 | 103 |
| unresolved questioners | 10 | 10 |
| explicit management-role-conflict calls | 2 | **5** |
| source-clean full calls | 9 | **7** |
| non-clean / refusal calls | 7 | **9** |
| per-call refusal reason | implicit scalar | **set** |

The structural layer is untouched. Only the respondent-role layer moved.

## The one-line law

`QNA_SOURCE_CLEAN` requires positive replayable same-revision respondent role/title support **and**
no incompatible same-revision role evidence. Absence of conflict is not cleanliness.

## Carrier lineage

The first correction carrier (`tfg1-r3-gold-source-clean-correction-20260828-v1`, direct-targeted to
Claude6) is terminal `UNCLAIMED_RECEIVER_UNAVAILABLE`; its candidate PR #6602 is closed at head
`8078d54ba89217b26559973b9149cc3fa0a092b7` and is candidate evidence only. This recovery carrier
inspected that diff to avoid retyping and then re-derived and re-verified every value against
current law and current main — which surfaced two defects in the candidate: a stale operation key
and a wrong ARQQ answer-turn count.

The exact next operation is `tfg1-r3-deterministic-transcript-format-hardening-20260828-v1` using
`research/earnings_intelligence/e3/TFG1_R3_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-28.md`.
