---
workstream: EARNINGS-EVENT-INTELLIGENCE-COMPILER
wave: TFG-0-R1
status: HOLD-FOR-SOL
operation_key: tfg0-transcript-format-census-20260827-v1
authority: architecture
decided_by: sol
created_at: 2026-08-27
supersedes:
  - agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-27-tfg0.md
---

# Earnings Event Intelligence Compiler — TFG-0 R1 continuation

## Mission just completed

Recover the generalization problem exposed by the frozen GOOGL E3-C failure without fitting the repair to GOOGL, inspect a pre-registered independent development corpus, freeze a transcript-local deterministic architecture, and leave a bounded TFG-1 implementation/holdout packet.

## Canonical predecessor closeout

E3-C refusal PR #6497 is now merged as `f244f0b34330cac9c98a815a3c0e97d0ba5b1d7f` from accepted exact head `be2f14ae1d9585d114bd06848feed98d74552d59`.

That merge makes the GOOGL source-format falsifier and `DEC:E3C-GOOGL-OOS-REFUSAL-SPENDS-EVENT` canonical. It does **not** complete E3-C. GOOGL is spent as clean OOS evidence; CAT/BAC/SNOW remain uninspected; E3-P remains locked.

## TFG-0 anti-leakage state

Operation `tfg0-transcript-format-census-20260827-v1` was pre-registered before body inspection.

Development selection came from the live `mastermind.tx-index/v1` by deterministic metadata/SHA ordering only:

- 2,909 eligible held revisions;
- exclude AAPL, GOOGL/GOOG, CAT, BAC, SNOW;
- select ranks 1–16 by `sha256(TFG0|pair|body_sha256)`;
- zero selected bodies inspected before the selection receipt was frozen.

An eight-call TFG-1 holdout is independently frozen as ranks 17–24. Its bodies remain **unopened**. Do not inspect them before the TFG-1 implementation head is frozen.

## What the development corpus proved

All 16 exact revisions byte replayed and contain real named analyst Q&A. The unchanged deterministic compiler succeeded on **0/16**:

- 11 `operator_intro_identity_unparsed`;
- 5 `zero_qa_boundaries`.

Across 1,524 segments, 672 roles are blank (44.1%). SCCO and COF are effectively roleless management formats but carry same-revision participant/title evidence. ARRY and CTRE show explicit same-revision role conflicts, proving segment role is evidence rather than unquestioned authority.

Post-freeze source-only adjudication froze:

- 110 real structural question handoffs;
- 95 direct Operator-name → next-speaker matches;
- 6 explicit full-name proxy handoffs (`on for` / `sitting in for`);
- 101 source-supported questioner handoffs under the closed direct/proxy law;
- 9 real handoffs whose questioner identity must remain unresolved;
- 2 explicit management-role-conflict calls (ARRY, CTRE);
- exactly 10 independently source-clean calls for all-or-nothing full-call reconstruction.

Therefore the initial `>=12/16` development bar was rejected as impossible under the already-binding fail-closed identity law. It is superseded, not loosened.

## Binding R1 architecture

Highest TFG-specific sources, in order:

1. `research/earnings_intelligence/e3/TFG0_R1_BOUNDARY_IDENTITY_AND_HOLDOUT_SCORING_AMENDMENT_2026-08-27.md`
2. `agentos/decisions/DEC-E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT.md`
3. `research/earnings_intelligence/e3/TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_ARCHITECTURE_FREEZE_2026-08-27.md`
4. `research/earnings_intelligence/e3/TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md`
5. `agentos/decisions/DEC-E3FMT-TRANSCRIPT-LOCAL-SOURCE-EVIDENCE-NORMALIZATION.md` where not superseded by R1.

R1 laws:

- terminal phrases (`go ahead`, line open/live, proceed) have zero boundary authority;
- a real question handoff remains a structural separator even when the questioner cannot be canonicalized;
- unresolved separators must prevent adjacent span contamination but cannot mint a canonical exchange;
- direct questioner requires exact source-name agreement under case/whitespace/honorific normalization only;
- a differing full-name next speaker is source-supported only when their first utterance explicitly says they are `on for` / `sitting in for` the Operator-named person;
- principal affiliation does not transfer to the proxy unless separately source-supported;
- no fuzzy/typo/nickname/initial repair;
- respondent role may come only from the same exact transcript revision: segment role and/or replayable participant/title declaration;
- explicit same-revision role conflict refuses;
- closed comparison aliases are exactly CEO↔Chief Executive Officer, CFO↔Chief Financial Officer, COO↔Chief Operating Officer; no `CIO`, no `etc.`;
- role remains non-null/source-supported; never invent generic `Management`.

## Correct development acceptance

TFG-1 must:

1. replay all 16 exact development SHAs;
2. recover all 110 structural separators with zero opening/queue/closing false positives;
3. resolve all 101 source-supported direct/proxy questioners;
4. keep all 9 unresolved handoffs separator-only/refused without adjacent contamination;
5. produce non-empty deterministic full-call reconstruction on **all 10 frozen source-clean calls**;
6. make the six source-conflicted calls fail only for their pre-adjudicated source identity/conflict reason, never terminal-dialect dependence;
7. preserve AAPL exactly 7 exchanges / 26 management answer turns / 68 replay spans;
8. hold hard safety: accepted unsupported 0, cross-event 0, accepted replay 100%;
9. contain no ticker/provider branch and no new store/model/control plane.

## Correct unseen-holdout law

Eight frozen ranks 17–24 are immutable and unopened.

After development gates are green:

1. freeze exact TFG-1 implementation head SHA;
2. only then open the eight exact holdout revisions and verify SHA;
3. before any compiler output, freeze a source-only `tfg1.holdout_source_adjudication.v1` classifying each fixed slot as `QNA_SOURCE_CLEAN`, `QNA_SOURCE_CONFLICTED`, `NO_QA_ADMISSION`, or `SOURCE_REVISION_MISMATCH`;
4. never replace, skip or rerank a slot;
5. if fewer than 6/8 are source-clean, stop `INSUFFICIENT_HOLDOUT_POWER`;
6. otherwise run the already-frozen compiler once;
7. every source-clean slot must produce non-empty full-call reconstruction;
8. conflicted slots must preserve all structural separators and fail only the pre-adjudicated source reason;
9. no-QA slots must create zero false Q&A boundaries;
10. boundary precision/recall and hard safety must remain 100%/0/0 as frozen;
11. **no code changes after holdout unseal**, whether or not the compiler has run yet.

The old bare `>=6/8 non-empty` outcome bar is superseded. Six of eight is now a source-clean **power gate**; when powered, compiler success is required on **all** clean slots.

## Canonical implementation handoff

Use only:

`research/earnings_intelligence/e3/TFG1_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_R1_2026-08-27.md`

The unsuffixed TFG-1 handoff is explicitly marked `SUPERSEDED` and must not be executed.

## Capability classification

TFG-0 is research/architecture only. If PR #6521 is Sol-accepted and merged, its capability state is **SPEC_ONLY**: the generalization method, development gold and unseen-holdout law are frozen, but no compiler behavior or production coverage has changed.

E3-B remains `PROVEN_LIVE / DONE`. Parent E3-C remains `GENERALIZATION_REFUSED_ON_SOURCE_FORMAT / in_progress`. TFG-1 must not be represented as E3-C completion. Only a later fresh untouched-production-OOS proof may close E3-C. E3-P remains locked.

## Exact next action

After Sol exact-head acceptance and merge of PR #6521, commission **one** strong frontier coding worker on `TFG1_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_R1_2026-08-27.md`.

Do not open the eight frozen holdout bodies before that worker freezes its implementation head. Do not inspect CAT/BAC/SNOW. Do not start E3-P.
