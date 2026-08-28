---
workstream: WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
session: claude/tfg1-r3-gold-correction-c6
model: opus
ended_because: complete
mission: >
  Land the truthful records/source-law correction produced by TFG-1 R2's second development-gold
  falsifier, so a fresh R3 implementation wave can be graded against correct source truth — without
  changing compiler behavior, touching the sealed holdout, or mutating either closed candidate PR.
state_before: >
  TFG-0 landed SPEC_ONLY (#6521). TFG-1 v1 terminated STOPPED_AT_DEVELOPMENT_GATE on a first gold
  falsifier and its records closeout merged as #6555. TFG-1 R2 then implemented the ratified R2 gold
  faithfully, reached a fully green structural half, and terminated at a SECOND gold falsifier: the
  gold declared 2 management-role-conflict calls where source shows 5, and 2 of the 9 source-clean
  calls contain management the revision never gives an office. PR #6591 is CLOSED UNMERGED. A first
  R3 attempt (#6602, Claude5) was closed unmerged as an unlawful pickup of a DIRECT_TARGETED
  operation. The holdout has never been opened through either wave.
changed:
  - path: research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json
    what: >
      New superseding R3 machine grading truth. Separator/questioner truth carried forward unchanged
      (113/97/6/103/10); management_role_conflict corrected to 5 calls; source-clean corrected to 7
      and refusal to 9; per-call source_blockers added as SETS; positive-role-support source-clean
      definition recorded. Generated deterministically from the R2 per_call block with invariant
      assertions, not hand-transcribed.
  - path: agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN.md
    what: Sol's ratification of the respondent-role source-clean correction, with the five rejected alternatives.
  - path: agentos/discoveries/DSC-E3FMT-ABSENCE-OF-ROLE-CONFLICT-IS-NOT-SOURCE-CLEAN.md
    what: The reusable constraint — absence of contradiction is not positive support; blockers must be sets.
  - path: agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-28-tfg1-r2-terminal.md
    what: This record — R2 terminal continuation.
  - path: research/earnings_intelligence/e3/TFG1_R3_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-28.md
    what: The sole active implementation packet for the successor R3 wave.
  - path: agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md
    what: R2 recorded terminal, R3 NOT_BUILT with its named operation key, R3 decision/discovery linked.
verified:
  - claim: The ratified R3 counts reconcile against the R2 gold's own per-call block
    command: "summation over per_call in tfg1_development_boundary_identity_adjudication_r2.json"
    result: "113 handoffs / 97 direct / 6 proxy / 10 unresolved / 103 supported; exactly six calls carry unresolved indices — BANR, CTRE, HTGC, LTH, MBLY, TRVI"
  - claim: Every ratified blocker set is consistent with the carried-forward per-call data
    command: "assertions in the generator: (unresolved_questioner in blockers) iff unresolved indices exist; (blockers empty) iff source_clean"
    result: "all assertions passed; generator refuses to emit otherwise"
  - claim: The R2 adjudication JSON and the R2 DEC are preserved byte-unchanged
    command: "git diff --name-only -- research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r2.json"
    result: "0 files; R2 blob remains 9017d327fd942a33f7716c8e0a86f72311a43131"
  - claim: The source-clean 7 and refusal 9 are exactly the R2 sets minus/plus ARQQ and FANG
    command: "set difference against summary.source_clean_call_pairs in the R2 JSON"
    result: "clean 9 - {ARQQ, FANG} = 7; refusal 7 + {ARQQ, FANG} = 9; sets disjoint, union = 16"
unverified:
  - claim: That ARQQ and FANG genuinely lack same-revision role support in their exact revisions
    what_would_verify: >
      Re-reading those two transcript revisions directly. This wave took Sol's ratification and the
      R2 wave's measurement as authority and did NOT re-open the source bodies; the records correction
      is not the place to re-adjudicate source. The successor implementation will exercise it.
unresolved:
  - Sol has not yet reviewed or landed this R3 records correction; until it lands, the successor implementation operation may not be commissioned.
  - ARQQ/2026Q2 and FANG/2026Q2 were not re-read from source in this wave. Their exclusion rests on Sol's ratification and the R2 wave's measurement, not on an independent re-reading here; the successor implementation is what will actually exercise it.
  - E3-C remains open. Neither this correction nor a successful R3 closes it — a fresh untouched-production OOS second-issuer proof (E3-OOS2) is still required, and E3-P stays locked behind it.
next_actions:
  - Sol reviews and lands this records correction on the R3 correction carrier.
  - Only after it lands, commission tfg1-r3-deterministic-transcript-format-hardening-20260828-v1 as a distinct implementation operation with its own carrier.
  - That wave grades against the R3 JSON, freezes an implementation head only when every development gate is green, then freezes source-only holdout slot adjudication BEFORE any compiler output.
  - E3-C fresh untouched-production OOS second-issuer proof remains downstream and is not unblocked by any of this.
do_not_redo:
  - The v1 and R2 operation keys are spent. Never reuse tfg1-deterministic-transcript-format-hardening-20260827-v1 or tfg1-r2-deterministic-transcript-format-hardening-20260827-v1.
  - Do not re-adjudicate 113/97/6/103/10, the 5-conflict set, or the 7-clean/9-refusal partition. Sol ratified them; they reconcile against source.
  - Do not amend the gold from inside an implementation wave. Both falsifiers were found by measuring the gold and stopping; that is the working pattern.
  - Do not record a single first-failure reason per refusing call. Blockers are sets.
  - Do not rescue MBLY, ARQQ or FANG with fuzzy names, nicknames, initials, prior-quarter titles or external biography.
  - PR #6591 and PR #6602 are closed evidence. Do not reopen, merge, force-push or cherry-pick them wholesale.
  - The holdout ranks 17-24 have never been opened across three waves. Do not open them before an implementation head is frozen.
danger_areas:
  - The holdout is single-use and non-replaceable. Any definition change that could alter QNA_SOURCE_CLEAN must land BEFORE slot adjudication is frozen, never after.
  - Transcript body SHAs are canonical-JSON hashes, not sha256 of the raw decompressed body; the raw convention falsely reports COF/2026Q2 as moved. See DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES.
  - The branch name implied by the R3 operation key already belongs to the closed #6602 candidate. On this shared clone that branch is present locally and remotely; cutting the obvious name lands you on it.
  - qa_exchange.v1 requires a non-null source-supported respondent role. Making it nullable to rescue a development call silently widens what the compiler may publish.
---

## Why R2 terminated

R2 implemented the frozen law faithfully. Its structural half was fully green — 16/16 byte replay,
113/113 separators, 103 supported questioners, 7/7 non-clean refusing, AAPL undisturbed at 7/26/68,
91 focused suites passing — and GOOGL demonstrated the generalization working: the detector recovered
all nine real analyst handoffs where the cue rule had seen only the one false pre-presentation
boundary, while GOOGL still refuses and still publishes nothing.

It stopped because the gold and the source disagreed twice more, and every route past those
disagreements was a move the frozen law forbids. The worker filed a `DECISION_REQUEST` rather than
choosing one, and Sol ruled YES on both.

The load-bearing judgment was refusing to defer. The holdout's source-only slot adjudication is
frozen before any compiler output, using a definition of `QNA_SOURCE_CLEAN`. Proceeding under the
old definition would have adjudicated holdout slots containing an untitled executive as clean,
missed them at compile time, and calibrated the power ruling on the wrong denominator — spending the
one non-replaceable asset in the program against a definition the development corpus had already
shown to be incomplete. A round trip is recoverable; that is not.

## Carrier history

- `tfg1-deterministic-transcript-format-hardening-20260827-v1` — terminal, first gold falsifier, records closeout merged as #6555.
- `tfg1-r2-deterministic-transcript-format-hardening-20260827-v1` — terminal, second gold falsifier, PR #6591 CLOSED UNMERGED, branch preserved as evidence.
- `tfg1-r3-gold-source-clean-correction-20260828-v1` — this records correction. PR #6602 was an unlawful pickup of the same key by a non-assigned seat and is CLOSED UNMERGED; its branch is preserved and untouched.
- `tfg1-r3-deterministic-transcript-format-hardening-20260828-v1` — named, NOT started, NOT commissioned by this record.

Holdout state across all of it: `holdout_bodies_inspected: 0`.
