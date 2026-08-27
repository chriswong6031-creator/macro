# TFG-1 R2 — Deterministic transcript-format hardening successor handoff

**Status:** FUTURE COMMISSION PACKET — do not implement until Macro PR #6555 is Sol-accepted and landed  
**Operation key:** `tfg1-r2-deterministic-transcript-format-hardening-20260827-v1`  
**Preferred operator:** one strong frontier coding worker  
**Repository:** `mastermindx-market-intelligence/macro` only  
**Expected return:** `BUILT_NOT_PROVEN` if development + single-use holdout gates pass, otherwise the exact named falsifier/blocker  

This is the sole active successor packet for the R2 implementation. It inherits the method/identity/role/holdout law from TFG-0 R1 and changes only the development gold corrected by `DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS`.

## BEFORE DOING ANY WORK — Slack handoff admission

If this operation is handed to an already-active Claude/Opus/Codex worker through Slack, the **initial Slack envelope itself** must require:

1. reply in that handoff thread with `ACK tfg1-r2-deterministic-transcript-format-hardening-20260827-v1`;
2. read the entire existing thread for Chairman/Sol instructions or amendments;
3. do not begin execution until both steps are complete.

This follows `DEC:SLACK-HANDOFF-INITIAL-ENVELOPE-REQUIRES-PREWORK-ACK`. ACK is transport evidence only; it is not Executive admission, Worker claim, RUNNING state or completion proof.

## Observable mission

Implement one deterministic transcript-local Q&A normalization method that satisfies the **ratified R2 development truth** without ticker/provider branches, guessed identity, model inference or production-publication widening; preserve AAPL exactly; then freeze the implementation and score it once against the still-unopened eight-slot holdout under the already-frozen source-only protocol.

## Why it matters

TFG-1 v1 correctly stopped before implementation freeze because the frozen development receipt omitted three genuine first-question separators. Sol ratified the correction rather than rewarding a gold-label error. R2 is the first implementation attempt against internally coherent pre-declared source truth. Passing R2 still does **not** close E3-C: a later fresh untouched production OOS event remains required.

## Authority / document precedence

At pickup, re-pin current Macro `main`, current protected Mastermind Sol Skillpack, current open E3/TFG PRs, and apply newer accepted source law if it collides. Governing sources in descending specificity:

1. `agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS.md`
2. `research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r2.json`
3. `agentos/decisions/DEC-E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT.md`
4. `research/earnings_intelligence/e3/TFG0_R1_BOUNDARY_IDENTITY_AND_HOLDOUT_SCORING_AMENDMENT_2026-08-27.md`
5. `research/earnings_intelligence/e3/TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_ARCHITECTURE_FREEZE_2026-08-27.md`
6. `research/earnings_intelligence/e3/TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md`
7. `research/earnings_intelligence/e3/TFG1_TRANSCRIPT_FORMAT_HOLDOUT_PREREG_2026-08-27.md` + `tfg1_transcript_format_holdout_selection.json`
8. `research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`
9. current E3-C refusal decision/workstream.

If a newer accepted E3/Q&A/identity law materially collides, **STOP and return Sol**.

## Verified current state to re-check at pickup

- TFG-0 architecture is `SPEC_ONLY`, merge `a2dd436722dd0e6c6cb1e17bfa1c888c706c15d0`.
- TFG-1 v1 terminated at a development-gold falsifier in PR #6555; it did not freeze implementation code and did not open the holdout.
- R2 machine gold contains **113** structural separators, **97** direct questioners, **6** explicit full-name proxies, **103** source-supported questioners, and **10** unresolved questioners.
- Source-clean full-call set is exactly nine calls: `OCSL/2026Q3`, `GEF/2026Q3`, `ARQQ/2026Q2`, `UPBD/2026Q2`, `SCCO/2026Q2`, `AGM/2026Q2`, `FANG/2026Q2`, `COF/2026Q2`, `KREF/2026Q2`.
- Seven expected non-clean/refusal calls: `MBLY/2026Q2`, `TRVI/2026Q2`, `CTRE/2026Q2`, `LTH/2026Q2`, `BANR/2026Q2`, `HTGC/2026Q2`, `ARRY/2026Q2`.
- MBLY #21 is a structural separator but unresolved questioner: Operator names Joshua Buchalter; next structured speaker is placeholder `Speaker 4`; first utterance identifies only `Lanny on for Josh`.
- AAPL production oracle remains transcript SHA `a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f`, exact **7 exchanges / 26 management answer turns / 68 replay spans**.
- Production accepted-revision admission remains AAPL-only.
- TFG transcript replay uses the canonical-JSON SHA convention recorded in `DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES`.

## Exact scope

Expected implementation surface:

- `engine/company_intelligence/qa_reconstruction.py`;
- `engine/company_intelligence/qa_exchange.py` only where the already-frozen backward-safe respondent evidence variant requires it;
- existing focused Q&A tests;
- one focused R2 TFG test module;
- at most one private helper under `engine/company_intelligence/` if clearly internal to the existing compiler.

Temporary read-only evaluation tooling is allowed only to execute exact held-source development/holdout proof and must be removed before final return unless an existing canonical fixture pattern requires a bounded checked-in fixture.

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
- edit the historical TFG-0 adjudication to hide the v1 gold falsifier.

## Deterministic method — unchanged from R1

- Terminal cue phrases (`go ahead`, `line open/live`, `proceed`, etc.) have **zero admission authority**.
- A true separator is an unambiguous question-bearing Operator/housekeeping handoff followed immediately by a non-housekeeping source turn.
- A separator remains load-bearing when questioner identity is unresolved; it must split windows but cannot mint canonical Q&A.
- Direct questioner identity requires exact source-name equality after case/whitespace/honorific normalization only.
- Differing full-name next speaker is accepted only when that speaker's first source utterance explicitly binds them as `on for` / `sitting in for` the Operator-named principal. Principal affiliation does not transfer.
- Placeholder/first-name-only proxy, typo/name mismatch and garbled handoff remain unresolved; no edit distance, nickname/initial map, external lookup or cross-revision repair.
- Respondent role evidence may come only from the same exact transcript revision: answer-segment role and/or replayable participant/title declaration.
- Explicit incompatible role evidence refuses. Missing role support refuses. Accepted respondent role remains non-null/source-supported.
- Closed role comparison aliases are only CEO↔Chief Executive Officer, CFO↔Chief Financial Officer, COO↔Chief Operating Officer; no CIO and no open-ended aliases.
- Bind every result to exact `document_id + document_sha256`; changed revision invalidates transient separator/identity evidence. Transcript source clock semantics remain unchanged and honest.

## Machine journey

### Development

`exact held revision → canonical-JSON replay → transcript-local deterministic normalization → 113 structural separators → direct/proxy/unresolved questioner state → same-revision respondent role evidence/conflict state → existing reconstruction/validation → non-empty full-call output or frozen typed refusal`

### Holdout

`all corrected development gates green → freeze exact implementation head + timestamp → only then open exact 8 frozen holdout bodies → byte replay → freeze source-only holdout adjudication before compiler output → power ruling → run frozen compiler once → score → STOP, with no code change after unseal`

### GOOGL regression

Only after the implementation + holdout result are frozen, rerun exact GOOGL Q2 as a known spent-falsifier regression. It can never be the fresh OOS clearance event.

## Strict TDD / ordered implementation sequence

1. Re-pin current `main`, Skillpack, R2 gold, current E3/TFG law and open overlapping PRs. Stop on collision.
2. Write/observe RED discriminators **before production behavior changes** for:
   - all 113 R2 separators, including MBLY #21, ARRY #31, KREF #15;
   - opening/prepared-speaker false handoffs rejected without terminal-cue authority;
   - 103 supported direct/proxy identities;
   - 10 unresolved separator-only cases, including MBLY #21;
   - unresolved separator preventing adjacent contamination;
   - punctuation-safe affiliations;
   - same-revision roster role support and evidence replay;
   - wrong revision/evidence span rejection;
   - exact CEO/CFO/COO role aliases with CIO mutation killed;
   - incompatible role evidence refusal and missing role refusal;
   - external/fuzzy inference mutant killed.
3. Implement the smallest deterministic transcript-local normalization inside the existing compiler path.
4. Implement structural separator + direct/proxy/unresolved questioner behavior.
5. Implement same-revision respondent-role resolution/conflict behavior.
6. Implement optional roster identity evidence only if backward-safe; otherwise STOP rather than changing canonical role semantics or inventing `qa_exchange.v2`.
7. Prove AAPL exact 7/26/68 and mutated-SHA refusal.
8. Execute the exact 16-call R2 development adjudication.
9. **Only if every development gate is green**, freeze exact implementation head SHA + timestamp. From that point onward, do not modify code after holdout unseal.
10. Open only the exact 8 frozen holdout revisions and verify their frozen SHAs using the canonical-JSON convention.
11. Before any holdout compiler output, create/freeze `tfg1.holdout_source_adjudication.v1` for every fixed slot using only source evidence.
12. `<6/8 QNA_SOURCE_CLEAN` => STOP `INSUFFICIENT_HOLDOUT_POWER`; do not replace/rerank.
13. If powered, run the already-frozen compiler **once**. Every clean slot must pass; conflicted/no-QA slots must behave exactly as pre-adjudicated; structural precision/recall and hard safety must remain green.
14. Any holdout miss => STOP. No patch/retest on this holdout.
15. Run exact GOOGL known-falsifier regression, still without code changes.
16. Run focused + planner-selected hosted CI/fences and remove temporary proof workflows.
17. Return DRAFT / HOLD-FOR-SOL. Do not merge or start E3-OOS2/E3-P.

## R2 development acceptance

Mandatory:

- exact 16 development SHAs replay under the canonical-JSON convention;
- **113/113** structural separators; zero false opening/queue/closing boundaries;
- **103/103** source-supported direct/proxy questioners resolved;
- **10/10** unresolved remain separator-only/refused with no adjacent contamination;
- **9/9** source-clean calls produce non-empty deterministic full-call reconstruction;
- seven non-clean calls fail only their frozen identity/conflict reason, never terminal dialect;
- MBLY #21 remains unresolved while structurally isolating spans;
- SCCO/COF roleless management only from replayable same-revision roster/title evidence;
- ARRY/CTRE explicit role conflicts refused;
- AAPL exact **7/26/68** and mutated SHA fail-closed;
- accepted unsupported 0; cross-event 0; accepted replay 100%;
- zero ticker/provider branch, model identity inference, new store/control plane or production-admission widening.

## Holdout acceptance — unchanged

The eight ranks 17–24 are immutable and remain unopened before implementation freeze. For every fixed slot source-adjudicate exactly one of:

- `QNA_SOURCE_CLEAN`
- `QNA_SOURCE_CONFLICTED`
- `NO_QA_ADMISSION`
- `SOURCE_REVISION_MISMATCH`

No replacement. Fewer than 6/8 source-clean => underpowered stop. If powered, the frozen compiler must succeed on **every** clean slot, preserve separators/refusal reason on conflicted slots, create no false Q&A on no-QA slots, and keep structural precision/recall + hard safety green. No code changes after unseal.

## Failure / stop conditions

STOP without rescue if:

- accepted source law collides;
- any frozen revision SHA moves under the canonical replay convention;
- any of the 113 development separators is missed or a false boundary appears;
- any 9 source-clean call fails;
- a non-clean call requires weakening its frozen refusal to pass;
- method needs ticker/provider-specific logic, guessed/external identity or model structure;
- respondent evidence cannot remain backward-safe;
- AAPL 7/26/68 changes;
- holdout is opened before implementation-head freeze;
- holdout source adjudication is not frozen before compiler output;
- holdout has <6 clean slots;
- any powered clean holdout slot fails;
- any code change occurs after holdout unseal;
- production issuer/admission/publication changes, CAT/BAC/SNOW inspection or E3-P seem necessary.

## Return packet to Sol

Return:

- operation key, worker/session identity, branch/PR, pickup/current-main collision receipt, exact final head;
- changed files + necessity;
- RED tests + observed failures, then GREEN commands/results;
- exact 16-call R2 matrix and 113/103/10/9/7 totals;
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

TFG-1 R2 does **not** close E3-C and cannot unlock E3-P. If Sol accepts a successful R2 return, the next operation is a fresh pre-registered untouched-production-OOS selection/proof. Only that later OOS pass can close parent E3-C.
