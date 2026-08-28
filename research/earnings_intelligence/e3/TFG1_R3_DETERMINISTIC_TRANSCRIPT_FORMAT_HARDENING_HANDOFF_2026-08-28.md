# TFG-1 R3 — Deterministic transcript-format hardening successor handoff

**Status:** FUTURE COMMISSION PACKET — do not implement until this records-only correction is Sol-accepted and landed
**Operation key:** `tfg1-r3-deterministic-transcript-format-hardening-20260828-v1`
**Preferred operator:** one strong frontier coding worker
**Repository:** `mastermindx-market-intelligence/macro` only
**Expected return:** `BUILT_NOT_PROVEN` if development + single-use holdout gates pass, otherwise the exact named falsifier/blocker

This is the sole active successor packet for the R3 implementation. It supersedes
`TFG1_R2_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-27.md`, which is retained as
historical evidence of the R2 commission. It inherits the method/identity/role/holdout law from
TFG-0 R1 unchanged and changes only the development gold corrected by
`DEC:E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN`.

## BEFORE DOING ANY WORK — Slack handoff admission

If this operation is handed to an already-active Claude/Opus/Codex worker through Slack, the
**initial Slack envelope itself** must require:

1. reply in that handoff thread with `ACK tfg1-r3-deterministic-transcript-format-hardening-20260828-v1`;
2. read the entire existing thread for Chairman/Sol instructions or amendments;
3. do not begin execution until both steps are complete.

This follows `DEC:SLACK-HANDOFF-INITIAL-ENVELOPE-REQUIRES-PREWORK-ACK`. ACK is transport evidence
only; it is not Executive admission, Worker claim, RUNNING state or completion proof.

## Observable mission

Implement one deterministic transcript-local Q&A normalization method that satisfies the **ratified
R3 development truth** without ticker/provider branches, guessed identity, model inference or
production-publication widening; preserve AAPL exactly; then freeze the implementation and score it
once against the still-unopened eight-slot holdout under the frozen source-only protocol using the
corrected `QNA_SOURCE_CLEAN` definition.

## Why it matters — and why this is the third attempt

Two prior operations stopped at development gates, and neither stop was a failure of the method:

- **v1** (`tfg1-deterministic-transcript-format-hardening-20260827-v1`) recovered all 110 frozen
  separators and found three the TFG-0 gold had omitted. Sol ratified the correction to 113.
- **R2** (`tfg1-r2-deterministic-transcript-format-hardening-20260827-v1`) recovered 113/113
  separators exactly and then found that the R2 gold's *respondent-role* layer contradicted the
  frozen identity-evidence amendment. Sol accepted that second falsifier and terminated R2.

Both stops were the system working. R3 is the first implementation attempt against a gold whose
structural layer *and* respondent-role layer have both been reconciled against source. Passing R3
still does **not** close E3-C: a later fresh untouched production OOS event remains required.

## Authority / document precedence

At pickup, re-pin current Macro `main`, current protected Mastermind Sol Skillpack, current open
E3/TFG PRs, and apply newer accepted source law if it collides. Governing sources in descending
specificity:

1. `agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN.md`
2. `research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json`
3. `agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS.md` (structural correction; still binding)
4. `agentos/decisions/DEC-E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT.md`
5. `research/earnings_intelligence/e3/TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md`
6. `research/earnings_intelligence/e3/TFG0_R1_BOUNDARY_IDENTITY_AND_HOLDOUT_SCORING_AMENDMENT_2026-08-27.md`
7. `research/earnings_intelligence/e3/TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_ARCHITECTURE_FREEZE_2026-08-27.md`
8. `research/earnings_intelligence/e3/TFG1_TRANSCRIPT_FORMAT_HOLDOUT_PREREG_2026-08-27.md` + `tfg1_transcript_format_holdout_selection.json`
9. `research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`
10. current E3-C refusal decision/workstream.

If a newer accepted E3/Q&A/identity law materially collides, **STOP and return Sol**.

## Verified current state to re-check at pickup

- TFG-0 architecture is `SPEC_ONLY`, merge `a2dd436722dd0e6c6cb1e17bfa1c888c706c15d0`.
- TFG-1 v1 and R2 are both TERMINAL at accepted development-gold falsifiers. Neither froze
  implementation code and neither opened the holdout.
- PR #6591 is **CLOSED UNMERGED**, DRAFT, exact evidence head
  `77fd9411c9cfb799b245c8138d2f1a40052d3b8d`, branch `claude/tfg1-r2-transcript-format-hardening`.
  It is preserved as evidence. Do **not** reopen, merge, reset, force-push or wholesale
  cherry-pick it. Its implementation commits may be read as **candidate** changes and re-derived
  under R3's own RED-first discipline, but they are not accepted implementation truth.
- PR #6602 is **CLOSED**, head `8078d54ba89217b26559973b9149cc3fa0a092b7`, branch
  `claude/tfg1-r3-gold-source-clean-correction`. It was the first correction carrier's records-only
  candidate; that carrier terminated `UNCLAIMED_RECEIVER_UNAVAILABLE` with no receiver ACK/START.
  Its six-file diff is **candidate evidence only** and must not be reopened, merged or mutated. The
  landed correction is the one shipped by
  `tfg1-r3-gold-source-clean-correction-recovery-20260828-v2`, which re-verified every value
  independently; where the two disagree, the landed records win.
- R3 machine gold contains **113** structural separators, **97** direct questioners, **6** explicit
  full-name proxies, **103** source-supported questioners, and **10** unresolved questioners —
  all carried over from R2 verbatim.
- Source-clean full-call set is exactly **seven** calls: `OCSL/2026Q3`, `GEF/2026Q3`, `UPBD/2026Q2`,
  `SCCO/2026Q2`, `AGM/2026Q2`, `COF/2026Q2`, `KREF/2026Q2`.
- **Nine** expected non-clean/refusal calls, each with a frozen blocker **set** (below).
- MBLY #21 is a structural separator but unresolved questioner: Operator names Joshua Buchalter;
  next structured speaker is placeholder `Speaker 4`; first utterance identifies only
  `Lanny on for Josh`.
- AAPL production oracle remains transcript SHA
  `a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f`, exact
  **7 exchanges / 26 management answer turns / 68 replay spans**.
- Production accepted-revision admission remains AAPL-only.
- TFG transcript replay uses the canonical-JSON SHA convention recorded in
  `DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES`. Raw decompressed hashing false-fails COF/2026Q2.

## The corrected source-clean law — read this before writing a test

`QNA_SOURCE_CLEAN` requires **all three**:

1. every real questioner handoff in the call is source-supported (direct exact-name match or
   explicit full-name proxy); **and**
2. every management answer that would be accepted into `qa_exchange.v1` has **positive replayable
   same-revision** respondent role/title support; **and**
3. no incompatible same-revision role evidence exists for that respondent.

**Absence of conflict is not cleanliness.** This is the whole content of the second falsifier. A
respondent with a blank segment role and no roster/title declaration is
`management_identity_insufficient` and refuses — it is not a clean respondent that merely happens
to have nothing contradicting it.

The discriminating pair the successor must get right:

- `SCCO/2026Q2` and `COF/2026Q2` publish **no** non-housekeeping segment role metadata, yet are
  **clean** — because those same revisions contain replayable participant/title declarations that
  positively bind their management respondents. They are the extended-respondent
  (`qa_respondent_identity_evidence.v1`, `method: transcript_roster`) path.

  Verified against source by the correction carrier — both revisions expose role vocabulary
  `{"Operator", ""}` only, so **every** management respondent here has a blank role exactly like
  ARQQ/FANG, and all four are still positively bound:

  | Call | Respondent | Q&A answers | Declaration (same revision) |
  |---|---|---|---|
  | SCCO/2026Q2 | Raúl Jacob Ruisánchez | segs 55–127 | seg 0, Operator: "Mr. Raúl Jacob, Vice President of Finance, Treasurer, and CFO" |
  | COF/2026Q2 | Richard Fairbank | segs 22–130 | seg 1, Jeff Norris: "Mr. Richard Fairbank, Capital One's Chairman and Chief Executive Officer" |
  | COF/2026Q2 | Andrew Young | segs 35–118 | seg 1, Jeff Norris: "Mr. Andrew Young, Capital One's Chief Financial Officer" |
  | COF/2026Q2 | Jeff Norris | segs 32–131 | seg 0, Operator: "Jeff Norris, Senior Vice President of Finance" |

  Note the declaring speaker is sometimes the Operator (a housekeeping role) and sometimes another
  manager, and the binding may name two people in one sentence. Do not assume a single declaring
  speaker or one-person-per-declaration.
- `ARQQ/2026Q2` and `FANG/2026Q2` also have blank roles, and are **not clean** — because no such
  declaration exists in their revisions. ARQQ's Nick Pointon answers 3 times inside the Q&A window
  (segments 34, 39, 41) and his full name occurs exactly once in the whole revision, in the role-free
  handoff "let me turn the call over to Nick Pointon" (segment 15); FANG's Chad McAllaster answers
  once (segment 92) and is referenced only by "I'll let Chad or Danny give the details" (segment 91).
  Neither phrase carries a role or title.

  > **Count the right turns.** Nick Pointon has **8 total speaking segments** but only **3
  > Q&A-window answer turns**; the other 5 (segments 16–20) are prepared remarks. An earlier
  > candidate record said "eight answer turns", conflating the two. The refusal does not depend on
  > the count — one unsupported accepted answer is sufficient — but a gate written against the wrong
  > number will not reproduce the frozen blocker set.

A test suite that cannot separate SCCO/COF from ARQQ/FANG has not implemented this law.

## Frozen per-call source-blocker sets

Blockers are **sets**, never one order-dependent first-failure reason. Reproduce each set exactly:
no missing blocker, no extra blocker. Never satisfy a call by weakening one of its frozen blockers.

| Call | Frozen `source_blockers` |
|---|---|
| MBLY/2026Q2 | `{unresolved_questioner}` |
| ARQQ/2026Q2 | `{missing_same_revision_respondent_role_support}` |
| TRVI/2026Q2 | `{unresolved_questioner}` |
| CTRE/2026Q2 | `{unresolved_questioner, management_role_conflict}` |
| LTH/2026Q2 | `{unresolved_questioner, management_role_conflict}` |
| BANR/2026Q2 | `{unresolved_questioner, management_role_conflict}` |
| FANG/2026Q2 | `{missing_same_revision_respondent_role_support}` |
| HTGC/2026Q2 | `{unresolved_questioner, management_role_conflict}` |
| ARRY/2026Q2 | `{management_role_conflict}` |

The five role-conflict calls and their same-revision evidence. Every row was re-read from source
bytes by the correction carrier; all seven respondent-layer bodies re-hashed to the frozen
`body_sha256` in `tfg0_transcript_format_development_corpus_selection.json`.

| Call | Respondent | Declared in-revision (segment) | Tagged answer-segment role |
|---|---|---|---|
| ARRY/2026Q2 | Neil Manning | "our President and COO" (seg 1) | `CFO` |
| CTRE/2026Q2 | James Callister | "Chief Investment Officer" (seg 2) | `CFO` |
| BANR/2026Q2 | Jill Rice | "our Chief Credit Officer" (seg 1) | `CFO` |
| LTH/2026Q2 | Erik Weaver | "Executive Vice President and CFO" (seg 1) | `CEO` |
| HTGC/2026Q2 | Seth Meyer | "President" (seg 1) | `CEO` |

Note that the declaration is not always in segment 1 (CTRE declares at segment 2) and is not always
made by the same kind of speaker — IR, CEO, and a blank-role speaker each make one of these
declarations. Do not hard-code the declaring segment index or the declaring speaker's role.

Closed comparison aliases stay exactly CEO↔Chief Executive Officer, CFO↔Chief Financial Officer,
COO↔Chief Operating Officer. **CIO is excluded on purpose** — CTRE tags its Chief Investment
Officer as CFO, and widening the aliases to absorb the new conflicts would silently re-admit CTRE.

## Exact scope

Expected implementation surface:

- `engine/company_intelligence/qa_reconstruction.py`;
- `engine/company_intelligence/qa_exchange.py` only where the already-frozen backward-safe respondent
  evidence variant requires it;
- existing focused Q&A tests;
- one focused R3 TFG test module;
- at most one private helper under `engine/company_intelligence/` if clearly internal to the existing
  compiler.

Temporary read-only evaluation tooling is allowed only to execute exact held-source
development/holdout proof and must be removed before final return unless an existing canonical
fixture pattern requires a bounded checked-in fixture.

## Explicit non-goals

Do **not**:

- edit `event_workspace.production_registry()` or register Alphabet;
- widen `scripts/refresh_event_workspaces.py` production coverage;
- widen the accepted AAPL-only production revision gate;
- edit Terminal/UI;
- change source acquisition/provider selection;
- change the event/company identity plane;
- create another Q&A/person/transcript/candidate store or publication plane;
- create another model-routing/control plane;
- use model/fuzzy/external biography identity inference;
- inspect CAT/BAC/SNOW;
- use GOOGL as fresh OOS evidence;
- start E3-OOS2 or E3-P;
- mutate, reopen or merge PR #6591 or its branch;
- mutate, reopen or merge PR #6602 or its branch `claude/tfg1-r3-gold-source-clean-correction`;
- edit the historical TFG-0 / R2 adjudications or their decision records to hide either falsifier.

## Deterministic method — unchanged from R1

- Terminal cue phrases (`go ahead`, `line open/live`, `proceed`, etc.) have **zero admission authority**.
- A true separator is an unambiguous question-bearing Operator/housekeeping handoff followed
  immediately by a non-housekeeping source turn.
- A separator remains load-bearing when questioner identity is unresolved; it must split windows but
  cannot mint canonical Q&A.
- Direct questioner identity requires exact source-name equality after case/whitespace/honorific
  normalization only.
- Differing full-name next speaker is accepted only when that speaker's first source utterance
  explicitly binds them as `on for` / `sitting in for` the Operator-named principal. Principal
  affiliation does not transfer.
- Placeholder/first-name-only proxy, typo/name mismatch and garbled handoff remain unresolved; no
  edit distance, nickname/initial map, external lookup or cross-revision repair.
- Respondent role evidence may come only from the same exact transcript revision: answer-segment role
  and/or replayable participant/title declaration.
- Explicit incompatible role evidence refuses. **Missing role support refuses.** Accepted respondent
  role remains non-null/source-supported.
- Bind every result to exact `document_id + document_sha256`; changed revision invalidates transient
  separator/identity evidence. Transcript source clock semantics remain unchanged and honest.

### Corpus facts measured by R2 that R3 should not rediscover the hard way

These were paid for by the R2 wave and are carried forward as evidence, not assumptions:

- The corpus uses **both** declaration orders — name-first (ARRY) and office-first (KREF) — and they
  are false friends for each other.
- An office phrase must **begin** with an office word after determiners are stripped.
- A candidate "name" that is itself an office phrase (e.g. `Chief Development Officer,`) will
  silently truncate the previous person's title if not rejected.
- Honorific periods (`Dr.`) are not sentence ends.
- GOOGL's older cue-based rule found only the *false* boundary at segment 0; the corrected rule
  recovers all nine real handoffs there while still refusing to publish.

## Machine journey

### Development

`exact held revision → canonical-JSON replay → transcript-local deterministic normalization → 113
structural separators → direct/proxy/unresolved questioner state → same-revision respondent role
evidence: positive support / conflict / absent → existing reconstruction/validation → non-empty
full-call output or frozen typed refusal set`

### Holdout

`all corrected development gates green → freeze exact implementation head + timestamp → only then
open exact 8 frozen holdout bodies → byte replay → freeze source-only holdout adjudication under the
CORRECTED QNA_SOURCE_CLEAN definition, before compiler output → power ruling → run frozen compiler
once → score → STOP, with no code change after unseal`

### GOOGL regression

Only after the implementation + holdout result are frozen, rerun exact GOOGL Q2 as a known
spent-falsifier regression. It can never be the fresh OOS clearance event.

## Strict TDD / ordered implementation sequence

1. Re-pin current `main`, Skillpack, R3 gold, current E3/TFG law and open overlapping PRs. Stop on
   collision.
2. Write/observe RED discriminators **before production behavior changes** for:
   - all 113 R3 separators, including MBLY #21, ARRY #31, KREF #15;
   - opening/prepared-speaker false handoffs rejected without terminal-cue authority;
   - 103 supported direct/proxy identities;
   - 10 unresolved separator-only cases, including MBLY #21;
   - unresolved separator preventing adjacent contamination;
   - punctuation-safe affiliations;
   - same-revision roster role support and evidence replay;
   - **positive role support required**: SCCO/COF accepted via roster/title evidence while
     ARQQ/FANG refuse `missing_same_revision_respondent_role_support`;
   - wrong revision/evidence span rejection;
   - exact CEO/CFO/COO role aliases with the CIO mutation killed;
   - all five role conflicts detected (ARRY, CTRE, BANR, LTH, HTGC);
   - **blocker sets**: CTRE/LTH/BANR/HTGC each report both blockers, not one;
   - external/fuzzy inference mutant killed.
3. Implement the smallest deterministic transcript-local normalization inside the existing compiler path.
4. Implement structural separator + direct/proxy/unresolved questioner behavior.
5. Implement same-revision respondent-role resolution, covering all three states: positive support,
   incompatible evidence, and absent evidence.
6. Implement optional roster identity evidence only if backward-safe; otherwise STOP rather than
   changing canonical role semantics or inventing `qa_exchange.v2`.
7. Prove AAPL exact 7/26/68 and mutated-SHA refusal.
8. Execute the exact 16-call R3 development adjudication, reporting a blocker **set** per call.
9. **Only if every development gate is green**, freeze exact implementation head SHA + timestamp.
   From that point onward, do not modify code after holdout unseal.
10. Open only the exact 8 frozen holdout revisions and verify their frozen SHAs using the
    canonical-JSON convention.
11. Before any holdout compiler output, create/freeze `tfg1.holdout_source_adjudication.v1` for every
    fixed slot using only source evidence and the **corrected** clean definition.
12. `<6/8 QNA_SOURCE_CLEAN` => STOP `INSUFFICIENT_HOLDOUT_POWER`; do not replace/rerank and do not
    revert to the falsified absence-of-conflict definition to reach power.
13. If powered, run the already-frozen compiler **once**. Every clean slot must pass;
    conflicted/no-QA slots must behave exactly as pre-adjudicated; structural precision/recall and
    hard safety must remain green.
14. Any holdout miss => STOP. No patch/retest on this holdout.
15. Run exact GOOGL known-falsifier regression, still without code changes.
16. Run focused + planner-selected hosted CI/fences and remove temporary proof workflows.
17. Return DRAFT / HOLD-FOR-SOL. Do not merge or start E3-OOS2/E3-P.

## R3 development acceptance

Mandatory:

- exact 16 development SHAs replay under the canonical-JSON convention;
- **113/113** structural separators; zero false opening/queue/closing boundaries;
- **103/103** source-supported direct/proxy questioners resolved;
- **10/10** unresolved remain separator-only/refused with no adjacent contamination;
- **7/7** source-clean calls produce non-empty deterministic full-call reconstruction;
- **9/9** non-clean calls fail with exactly their frozen blocker set, never terminal dialect;
- MBLY #21 remains unresolved while structurally isolating spans;
- SCCO/COF roleless management accepted **only** from replayable same-revision roster/title evidence;
- ARQQ/FANG refuse `missing_same_revision_respondent_role_support`;
- ARRY/CTRE/BANR/LTH/HTGC explicit role conflicts refused;
- AAPL exact **7/26/68** and mutated SHA fail-closed;
- accepted unsupported 0; cross-event 0; accepted replay 100%;
- zero ticker/provider branch, model identity inference, new store/control plane or
  production-admission widening.

## Holdout acceptance — structurally unchanged

The eight ranks 17–24 are immutable and remain unopened before implementation freeze. For every
fixed slot source-adjudicate exactly one of:

- `QNA_SOURCE_CLEAN` (under the corrected positive-role-support definition)
- `QNA_SOURCE_CONFLICTED`
- `NO_QA_ADMISSION`
- `SOURCE_REVISION_MISMATCH`

No replacement. Fewer than 6/8 source-clean => underpowered stop. If powered, the frozen compiler
must succeed on **every** clean slot, preserve separators/refusal reason on conflicted slots, create
no false Q&A on no-QA slots, and keep structural precision/recall + hard safety green. No code
changes after unseal.

The corrected definition is strictly narrower than R2's, so the holdout clean count can only fall.
An underpowered stop is a legitimate scientific outcome and is **not** grounds to relax the
definition.

## Failure / stop conditions

STOP without rescue if:

- accepted source law collides;
- any frozen revision SHA moves under the canonical replay convention;
- any of the 113 development separators is missed or a false boundary appears;
- any of the 7 source-clean calls fails;
- a non-clean call requires weakening any blocker in its frozen set to pass;
- a non-clean call reports a blocker set different from its frozen set;
- method needs ticker/provider-specific logic, guessed/external identity or model structure;
- respondent evidence cannot remain backward-safe;
- AAPL 7/26/68 changes;
- holdout is opened before implementation-head freeze;
- holdout source adjudication is not frozen before compiler output;
- holdout has <6 clean slots;
- any powered clean holdout slot fails;
- any code change occurs after holdout unseal;
- production issuer/admission/publication changes, CAT/BAC/SNOW inspection or E3-P seem necessary.

**A third development-gold falsifier is a legitimate return.** If R3 measures source truth that
contradicts the R3 gold, return it as a named falsifier with exact evidence. Do not amend your own
grading truth, and do not open the holdout to break the tie.

## Return packet to Sol

Return:

- operation key, worker/session identity, branch/PR, pickup/current-main collision receipt, exact final head;
- changed files + necessity;
- RED tests + observed failures, then GREEN commands/results;
- exact 16-call R3 matrix with per-call blocker sets and 113/103/10/7/9 totals;
- AAPL 7/26/68 + mutated-SHA refusal;
- hard-safety totals;
- implementation-freeze SHA + timestamp;
- proof holdout bodies were unopened before freeze;
- source-only holdout adjudication receipt identity/hash created before compiler output;
- exact 8-slot holdout matrix + source-clean power ruling + frozen-compiler score;
- proof zero code changes after holdout unseal;
- exact GOOGL regression after freeze;
- hosted CI/fences exact-head;
- confirmation production admission remains AAPL-only;
- final classification `BUILT_NOT_PROVEN` or exact named falsifier/blocker.

## Continuation

TFG-1 R3 does **not** close E3-C and cannot unlock E3-P. If Sol accepts a successful R3 return, the
next operation is a fresh pre-registered untouched-production-OOS selection/proof. Only that later
OOS pass can close parent E3-C.
