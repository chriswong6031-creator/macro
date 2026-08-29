# TFG-1 R3 — Deterministic transcript-format hardening successor handoff

**Status:** FUTURE COMMISSION PACKET — `NOT_BUILT`. Do not implement until this records correction is Sol-accepted and landed.
**Operation key:** `tfg1-r3-deterministic-transcript-format-hardening-20260828-v1`
**Preferred operator:** one strong frontier coding worker
**Repository:** `mastermindx-market-intelligence/macro` only
**Expected return:** `BUILT_NOT_PROVEN` if development + single-use holdout gates pass, otherwise the exact named falsifier/blocker

This is the sole active successor packet for the R3 implementation. It inherits the method/identity/role/holdout law from TFG-0 R1 unchanged, inherits the structural gold from `DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS` unchanged, and changes only the respondent-role layer corrected by `DEC:E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN`.

## BEFORE DOING ANY WORK — Slack handoff admission

If this operation is handed to an already-active Claude/Opus/Codex worker through Slack, the **initial Slack envelope itself** must require:

1. reply in that handoff thread with `ACK tfg1-r3-deterministic-transcript-format-hardening-20260828-v1`;
2. read the entire existing thread for Chairman/Sol instructions or amendments;
3. do not begin execution until both steps are complete.

This follows `DEC:SLACK-HANDOFF-INITIAL-ENVELOPE-REQUIRES-PREWORK-ACK`. ACK is transport evidence only; it is not Executive admission, Worker claim, RUNNING state or completion proof.

**Additionally, and specific to this arc:** three consecutive R3 records carriers closed unmerged on receiver identity rather than content (#6602, #6606 post-STOP, #6608 `RECEIVER_IDENTITY_UNRESOLVED` despite green exact-head CI). Confirm a concrete receiver binding exists on the carrier thread before starting, and re-read that thread immediately before ACK — a STOP can land in the gap between a search result and an ACK.

## Observable mission

Implement one deterministic transcript-local Q&A normalization method that satisfies the **ratified R3 development truth** — including POSITIVE same-revision respondent role support — without ticker/provider branches, guessed identity, model inference or production-publication widening; preserve AAPL exactly; then freeze the implementation and score it once against the still-unopened eight-slot holdout under the already-frozen source-only protocol.

## Why it matters

R2 stopped at a SECOND development-gold falsifier: the R2 gold graded ARQQ and FANG source-clean because no role CONFLICT existed, when neither revision offers any positive role support at all. An implementation graded against R2 would have been trained to publish `qa_exchange.v1` respondents with no replayable role evidence. R3 is the first implementation attempt against a gold whose respondent-role layer has been verified against source bytes. Passing R3 still does **not** close E3-C: a later fresh untouched production OOS event remains required.

## Authority / document precedence

At pickup, re-pin current Macro `main`, current protected Mastermind Sol Skillpack, current open E3/TFG PRs, and apply newer accepted source law if it collides. Governing sources in descending specificity:

1. `agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R3-RESPONDENT-ROLE-SOURCE-CLEAN.md`
2. `research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r3.json`
3. `agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS.md` *(structural layer; not withdrawn)*
4. `agentos/decisions/DEC-E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT.md`
5. `research/earnings_intelligence/e3/TFG0_R1_BOUNDARY_IDENTITY_AND_HOLDOUT_SCORING_AMENDMENT_2026-08-27.md`
6. `research/earnings_intelligence/e3/TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_ARCHITECTURE_FREEZE_2026-08-27.md`
7. `research/earnings_intelligence/e3/TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md`
8. `research/earnings_intelligence/e3/TFG1_TRANSCRIPT_FORMAT_HOLDOUT_PREREG_2026-08-27.md` + `tfg1_transcript_format_holdout_selection.json`
9. `research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`
10. current E3-C refusal decision/workstream.

The R2 adjudication JSON is **superseded as machine grading truth** and is retained byte-unchanged as falsified evidence. Do not grade against it.

If a newer accepted E3/Q&A/identity law materially collides, **STOP and return Sol**.

## Verified current state to re-check at pickup

- TFG-0 architecture is `SPEC_ONLY`, merge `a2dd436722dd0e6c6cb1e17bfa1c888c706c15d0`.
- TFG-1 v1 terminated at the FIRST (structural) development-gold falsifier in PR #6555.
- TFG-1 R2 terminated at the SECOND (respondent-role) falsifier; PR #6591 closed unmerged, Sol review `5048161769` accepted D1 and D2.
- R3 machine gold contains **113** structural separators, **97** direct questioners, **6** explicit full-name proxies, **103** source-supported questioners, and **10** unresolved questioners — all carried over from R2 verbatim.
- Management-role-conflict calls are exactly **five**: `ARRY/2026Q2`, `CTRE/2026Q2`, `BANR/2026Q2`, `LTH/2026Q2`, `HTGC/2026Q2`.
- Source-clean full-call set is exactly **seven** calls: `OCSL/2026Q3`, `GEF/2026Q3`, `UPBD/2026Q2`, `SCCO/2026Q2`, `AGM/2026Q2`, `COF/2026Q2`, `KREF/2026Q2`.
- Expected refusal set is exactly **nine** calls: `MBLY/2026Q2`, `ARQQ/2026Q2`, `TRVI/2026Q2`, `CTRE/2026Q2`, `LTH/2026Q2`, `BANR/2026Q2`, `FANG/2026Q2`, `HTGC/2026Q2`, `ARRY/2026Q2`.
- Refusal reasons are **SETS**, not order-dependent first failures. `CTRE`, `LTH`, `BANR` and `HTGC` each carry BOTH `unresolved_questioner` and `management_role_conflict`.
- MBLY #21 is a structural separator but unresolved questioner: Operator names Joshua Buchalter; next structured speaker is placeholder `Speaker 4`; first utterance identifies only `Lanny on for Josh`.
- AAPL production oracle remains transcript SHA `a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f`, exact **7 exchanges / 26 management answer turns / 68 replay spans**.
- Production accepted-revision admission remains AAPL-only.
- TFG transcript replay uses the canonical-JSON SHA convention recorded in `DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES`.

## The corrected law this operation must implement

`QNA_SOURCE_CLEAN` — a call is source-clean for full-call reconstruction only when:

1. every real questioner handoff is source-supported under the frozen direct/proxy law; **and**
2. every management answer that would be accepted into `qa_exchange.v1` has **positive replayable same-revision** respondent role/title support; **and**
3. no incompatible same-revision role evidence exists for that respondent.

**Absence of conflict is not cleanliness.** Condition 2 is what R2 lacked.

### The discriminator that proves the implementation

`SCCO/2026Q2` and `COF/2026Q2` **also** publish blank segment roles and **are** source-clean, because those revisions carry replayable same-revision title declarations in text (COF: *"Andrew Young, Capital One's Chief Financial Officer"*). `ARQQ/2026Q2` (Nick Pointon) and `FANG/2026Q2` (Chad McAllaster) do not — FANG's full name never appears in any segment text at all.

**A method that refuses every blank segment role is exactly as wrong as one that accepts every blank segment role.** Separate these pairs on positive same-revision evidence, never on blankness. Both mutants must be killed by tests.

### Closed escape hatches

- Empty/generic role breaks `qa_exchange.v1`; filling the role is guessed identity.
- Relaxing conflict detection to clear BANR/LTH/HTGC also stops detecting ARRY/CTRE.
- Widening the CEO/CFO/COO alias table re-admits CTRE — CIO is excluded on purpose, because CTRE tags its Chief Investment Officer as CFO.

## Exact scope

Expected implementation surface:

- `engine/company_intelligence/qa_reconstruction.py`;
- `engine/company_intelligence/qa_exchange.py` only where the already-frozen backward-safe respondent evidence variant requires it;
- existing focused Q&A tests;
- one focused R3 TFG test module — **it must be wired into a CI job**; R2's test module was wired into none, so all 35 of its discriminators would have been dead weight;
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
- edit the historical TFG-0 or R2 adjudications, or their DECs, to hide either gold falsifier.

## Deterministic method — unchanged from R1

- Terminal cue phrases (`go ahead`, `line open/live`, `proceed`, etc.) have **zero admission authority**.
- A true separator is an unambiguous question-bearing Operator/housekeeping handoff followed immediately by a non-housekeeping source turn.
- A separator remains load-bearing when questioner identity is unresolved; it must split windows but cannot mint canonical Q&A.
- Direct questioner identity requires exact source-name equality after case/whitespace/honorific normalization only.
- Differing full-name next speaker is accepted only when that speaker's first source utterance explicitly binds them as `on for` / `sitting in for` the Operator-named principal. Principal affiliation does not transfer.
- Placeholder/first-name-only proxy, typo/name mismatch and garbled handoff remain unresolved; no edit distance, nickname/initial map, external lookup or cross-revision repair.
- Respondent role evidence may come only from the same exact transcript revision: answer-segment role and/or replayable participant/title declaration.
- Explicit incompatible role evidence refuses. **Missing role support refuses.** Accepted respondent role remains non-null/source-supported.
- Closed role comparison aliases are only CEO↔Chief Executive Officer, CFO↔Chief Financial Officer, COO↔Chief Operating Officer; no CIO and no open-ended aliases.
- Bind every result to exact `document_id + document_sha256`; changed revision invalidates transient separator/identity evidence. Transcript source clock semantics remain unchanged and honest.

## Machine journey

### Development

`exact held revision → canonical-JSON replay → transcript-local deterministic normalization → 113 structural separators → direct/proxy/unresolved questioner state → same-revision respondent role evidence: positive support / incompatible / missing → existing reconstruction/validation → non-empty full-call output or frozen typed refusal SET`

### Holdout

`all corrected development gates green → freeze exact implementation head + timestamp → only then open exact 8 frozen holdout bodies → byte replay → freeze source-only holdout adjudication before compiler output → power ruling → run frozen compiler once → score → STOP, with no code change after unseal`

### GOOGL regression

Only after the implementation + holdout result are frozen, rerun exact GOOGL Q2 as a known spent-falsifier regression. It can never be the fresh OOS clearance event.

## Strict TDD / ordered implementation sequence

1. Re-pin current `main`, Skillpack, R3 gold, current E3/TFG law and open overlapping PRs. Stop on collision.
2. Write/observe RED discriminators **before production behavior changes** for:
   - all 113 R3 separators, including MBLY #21, ARRY #31, KREF #15;
   - opening/prepared-speaker false handoffs rejected without terminal-cue authority;
   - 103 supported direct/proxy identities;
   - 10 unresolved separator-only cases, including MBLY #21;
   - unresolved separator preventing adjacent contamination;
   - punctuation-safe affiliations;
   - **positive same-revision role support required** — ARQQ and FANG refuse `missing_same_revision_respondent_role_support`;
   - **blank-role-blanket-refusal mutant killed** — SCCO and COF stay clean on roster/title declarations;
   - same-revision roster role support and evidence replay, with the evidence surviving to publication (R2 silently stripped roster evidence at the `qa_exchange` layer, which would have published a roster-derived role with no replayable support);
   - wrong revision/evidence span rejection;
   - exact CEO/CFO/COO role aliases with CIO mutation killed;
   - **alias-widening mutant killed** — any table wide enough to clear BANR/LTH/HTGC must re-break CTRE/ARRY and fail;
   - incompatible role evidence refusal for all five conflict calls;
   - **blocker SET assertions** — CTRE/LTH/BANR/HTGC each report BOTH blockers, not one;
   - external/fuzzy inference mutant killed.
3. Implement the smallest deterministic transcript-local normalization inside the existing compiler path.
4. Implement structural separator + direct/proxy/unresolved questioner behavior.
5. Implement same-revision respondent-role resolution: positive support, incompatible, and missing.
6. Implement optional roster identity evidence only if backward-safe; otherwise STOP rather than changing canonical role semantics or inventing `qa_exchange.v2`.
7. Prove AAPL exact 7/26/68 and mutated-SHA refusal.
8. Execute the exact 16-call R3 development adjudication.
9. **Only if every development gate is green**, freeze exact implementation head SHA + timestamp. From that point onward, do not modify code after holdout unseal.
10. Open only the exact 8 frozen holdout revisions and verify their frozen SHAs using the canonical-JSON convention.
11. Before any holdout compiler output, create/freeze `tfg1.holdout_source_adjudication.v1` for every fixed slot using only source evidence, under the **corrected** definition.
12. `<6/8 QNA_SOURCE_CLEAN` => STOP `INSUFFICIENT_HOLDOUT_POWER`; do not replace/rerank.
13. If powered, run the already-frozen compiler **once**. Every clean slot must pass; conflicted/no-QA slots must behave exactly as pre-adjudicated; structural precision/recall and hard safety must remain green.
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
- the **nine** non-clean calls fail for **exactly their frozen blocker SET** and no other reason, never terminal dialect;
- MBLY #21 remains unresolved while structurally isolating spans;
- SCCO/COF roleless management accepted **only** from replayable same-revision roster/title evidence;
- ARQQ/FANG refused for missing same-revision respondent role support;
- ARRY/CTRE/BANR/LTH/HTGC explicit role conflicts refused;
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

**Power warning, pre-registered here.** The corrected definition is strictly NARROWER than R2's, so it can only LOWER the holdout clean count. An `INSUFFICIENT_HOLDOUT_POWER` stop is a foreseeable and legitimate scientific outcome and must **not** be rescued by reverting to the falsified absence-of-conflict definition.

## Failure / stop conditions

STOP without rescue if:

- accepted source law collides;
- any frozen revision SHA moves under the canonical replay convention;
- any of the 113 development separators is missed or a false boundary appears;
- any of the 7 source-clean calls fails;
- a non-clean call requires weakening its frozen blocker SET to pass;
- clearing a role conflict requires widening the closed alias table;
- refusing ARQQ/FANG requires refusing SCCO/COF too;
- method needs ticker/provider-specific logic, guessed/external identity or model structure;
- respondent evidence cannot remain backward-safe, or roster evidence cannot survive to publication;
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
- exact 16-call R3 matrix and 113/103/10/7/9 totals, with per-call blocker SETS;
- proof the R3 test module is wired into a real CI job;
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

TFG-1 R3 does **not** close E3-C and cannot unlock E3-P. If Sol accepts a successful R3 return, the next operation is a fresh pre-registered untouched-production-OOS selection/proof. Only that later OOS pass can close parent E3-C.
