# TFG-1 R1 — Deterministic transcript-format hardening handoff

**Status:** FUTURE COMMISSION PACKET — do not start until TFG-0 is Sol-accepted/landed and the E3-C refusal carrier is canonically reconciled  
**Preferred operator:** one strong frontier coding worker  
**Repository:** `mastermindx-market-intelligence/macro` only  
**Expected return class:** `BUILT_NOT_PROVEN` for broader production coverage; no production publication in this wave

This R1 handoff supersedes `TFG1_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-27.md`.

## Observable mission

Generalize the existing deterministic Q&A compiler across the frozen multi-format transcript corpus without ticker/provider branches, identity guesses or partial production publication. Preserve AAPL exactly. Prove the frozen implementation against the independently frozen unseen format holdout, then return to Sol without starting a fresh production OOS event.

## Why it matters

GOOGL falsified the AAPL-calibrated format assumptions. TFG-0 then selected 16 development revisions from 2,909 eligible held calls **before body inspection** and measured the unchanged compiler at 0/16. The source-only adjudication found 110 real Q&A handoffs across multiple dialects; terminal phrases are not a reliable boundary law, segment roles are incomplete, and some transcript metadata conflicts with explicit same-revision title text.

The product job is not “make regexes pass GOOGL.” It is to create one source-native deterministic method that can safely turn heterogeneous earnings transcripts into auditable `qa_exchange.v1` structure while refusing genuinely unsupported identity.

## Authority / precedence

At pickup, re-pin current `main`. Apply the newest accepted version of these sources in this order:

1. `TFG0_R1_BOUNDARY_IDENTITY_AND_HOLDOUT_SCORING_AMENDMENT_2026-08-27.md`
2. `DEC-E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT.md`
3. `TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_ARCHITECTURE_FREEZE_2026-08-27.md`
4. `TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md`
5. `tfg0_development_boundary_identity_adjudication.json`
6. `tfg0_respondent_identity_feasibility_receipt.json`
7. `tfg0_transcript_format_census_receipt.json`
8. `TFG1_TRANSCRIPT_FORMAT_HOLDOUT_PREREG_2026-08-27.md` + `tfg1_transcript_format_holdout_selection.json`
9. `E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`
10. current landed E3-C refusal decision/workstream state.

If a newer accepted E3/Q&A/identity law collides, STOP and return to Sol.

## Verified current baseline to re-check at pickup

Development corpus:

- 16 exact held revisions; 16/16 byte replay;
- unchanged compiler: 0/16 success;
- 11 `operator_intro_identity_unparsed`, 5 `zero_qa_boundaries`;
- 1,524 segments; 672 blank roles (44.1%);
- 110 source-adjudicated real question handoffs;
- 95 direct next-speaker matches;
- 6 explicit full-name proxy handoffs;
- 9 unresolved questioner handoffs;
- source-clean full-call set = exactly 10 calls: `OCSL/2026Q3`, `MBLY/2026Q2`, `GEF/2026Q3`, `ARQQ/2026Q2`, `UPBD/2026Q2`, `SCCO/2026Q2`, `AGM/2026Q2`, `FANG/2026Q2`, `COF/2026Q2`, `KREF/2026Q2`.

AAPL production oracle:

- transcript SHA `a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f`;
- 7 exchanges / 26 management answer turns / 68 replay spans.

Production acceptance remains AAPL-revision-gated. TFG-1 must not widen it.

## Exact scope

Expected implementation surface:

- `engine/company_intelligence/qa_reconstruction.py`;
- `engine/company_intelligence/qa_exchange.py`;
- existing Q&A tests;
- one focused TFG-1 test module;
- at most one private helper under `engine/company_intelligence/` if clearly an implementation detail of the existing compiler.

Temporary read-only proof workflow/fixtures are allowed only to execute exact held-source evaluation and must be removed before final return unless an existing canonical test-fixture pattern requires a bounded checked-in fixture.

## Explicit non-goals

Do **not** edit or widen:

- `event_workspace.production_registry()` or Alphabet registration;
- `scripts/refresh_event_workspaces.py` production coverage;
- accepted AAPL-only production revision admission;
- Terminal repository/UI;
- source acquisition/provider selection;
- event/company identity plane;
- any Q&A/candidate/person/transcript store;
- model routing;
- FIF, Prophet, scoring, sentiment, beat/miss, rank/size/gate/trade;
- CAT/BAC/SNOW bodies;
- E3-P.

No external biography/title lookup.

## Complete machine journey

### Development

```text
exact held transcript revision
→ deterministic transcript-local normalization
→ structural Q&A separators
→ direct / explicit-proxy / unresolved questioner state
→ same-revision respondent role evidence + conflict state
→ existing deterministic exchange reconstruction
→ existing canonical qa_exchange validation in development/shadow context
→ full-call non-empty OR typed fail-closed result
```

### Holdout

```text
dev gates green
→ freeze implementation head SHA
→ open exact 8 frozen holdout bodies
→ byte replay
→ source-only holdout adjudication receipt (NO compiler output yet)
→ freeze that receipt
→ run the frozen compiler once
→ score against adjudication
→ STOP; no code change after unseal
```

### Known GOOGL regression

Only after the implementation and holdout result are frozen, rerun exact GOOGL Q2 as known regression. It can never be the fresh OOS clearance event.

## Deterministic method

### 1. Structural separators

Terminal cue phrases (`go ahead`, `line open/live`, `proceed`) have zero admission authority.

A true separator requires an Operator/housekeeping **question-bearing named handoff** immediately followed by a non-housekeeping source turn. Opening prepared-speaker handoffs, generic queue instructions and closing returns do not qualify.

Even an unresolved questioner handoff remains a separator so adjacent exchanges cannot absorb its spans.

### 2. Direct questioner

Operator name and immediate next structured speaker must match under whitespace/case/honorific normalization only.

### 3. Explicit proxy questioner

If Operator names X and next structured full-name speaker is Y, accept Y only when Y's first utterance explicitly says Y is `on for`, `sitting in for`, or equivalent on behalf of X.

- canonical name = Y;
- X's affiliation does not transfer to Y;
- proxy affiliation stays unresolved unless same-revision source directly supports it.

Structured placeholders + first-name-only self identification remain unresolved. One-character differences remain conflicts; no edit distance.

### 4. Respondent role

Evidence may come only from the same exact transcript revision:

- answer-segment role;
- replayable participant/title declaration;
- compatible combination.

No external/person history/prior-quarter inference.

Role comparison aliases are exactly:

- `CEO` ↔ `Chief Executive Officer`;
- `CFO` ↔ `Chief Financial Officer`;
- `COO` ↔ `Chief Operating Officer`.

No `etc.` and no `CIO` alias. Other roles compare only as exact normalized title components. Explicit incompatible evidence => `management_identity_conflict`. Missing support => `management_identity_insufficient`.

### 5. Canonical roster evidence

Legacy respondent remains:

```text
{name, role, identity_state, span_indexes}
```

Roster/title-derived roles use the frozen optional nested `identity_evidence` variant from `TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md`, with same-revision replayable role source spans.

Production remains AAPL-only, so no extended respondent may be published by TFG-1. If Macro cannot implement the dual variant backward-safely, STOP; do not make `role` nullable or invent `qa_exchange.v2`.

## Data / identity / clock / correction law

- bind every result to exact `document_id + document_sha256`;
- changed SHA invalidates all transient boundary/roster evidence;
- no title/questioner evidence crosses revisions;
- transcript native availability semantics unchanged (`null/unknown` stays honest);
- no ticker key becomes durable identity;
- no source-supported name/role is inferred from another event;
- affiliation may be unresolved; accepted respondent role may not.

## TDD / ordered implementation sequence

1. Re-pin current Macro main, current TFG/E3 law and open overlapping PRs. Stop on collision.
2. Write RED discriminators before production behavior changes:
   - opening `go ahead` handoff rejected;
   - multiple valid terminal dialects recognized without terminal-cue authority;
   - all 110 frozen dev separators represented;
   - direct questioner exact match;
   - explicit full-name proxy relation accepted with affiliation unresolved;
   - placeholder/first-name proxy, typo/name mismatch and garbled handoff remain unresolved;
   - unresolved separator splits windows and cannot contaminate neighbors;
   - abbreviation-safe affiliations (`J.P. Morgan`, `D.A. Davidson`, `B. Riley`);
   - roster-supported role accepted with replayable evidence;
   - wrong revision/evidence span rejected;
   - exact closed CEO/CFO/COO comparison map; `CIO` mutation killed;
   - incompatible role evidence refuses;
   - no role evidence refuses;
   - external/fuzzy inference mutant killed.
3. Implement smallest deterministic transcript-local normalization inside the existing compiler path.
4. Implement structural separator + direct/proxy questioner logic.
5. Implement same-revision respondent role resolution/conflict law.
6. Implement/test optional roster identity evidence without widening production revision admission.
7. Verify AAPL exact 7/26/68 and changed-AAPL-SHA refusal.
8. Run frozen development adjudication:
   - 110/110 structural separators; zero false opening/queue/closing boundaries;
   - 101/101 direct/proxy source-supported questioners;
   - 9/9 unresolved stay separator-only/refused;
   - all 10 frozen source-clean calls non-empty;
   - six source-conflicted calls fail only for frozen identity/conflict reasons, not cue dialect;
   - hard safety green.
9. Freeze exact implementation head SHA and timestamp. **No further code changes are allowed after holdout unseal.**
10. Open eight frozen holdout revisions, byte replay exact SHAs.
11. Before any holdout compiler run, create/freeze `tfg1.holdout_source_adjudication.v1` using R1 source-only rubric.
12. If fewer than 6/8 slots are `QNA_SOURCE_CLEAN`, STOP `INSUFFICIENT_HOLDOUT_POWER`; no replacement.
13. Otherwise run frozen compiler once:
   - every clean slot non-empty;
   - conflicted slots preserve separators and fail only pre-adjudicated source reason;
   - no-QA slots create no false boundary;
   - structural precision/recall 100%; hard safety green.
14. If any holdout gate misses, STOP. Do not patch and retest the same holdout.
15. Run exact GOOGL known-falsifier regression, still no code changes.
16. Run focused + planner-selected hosted CI; remove temporary proof workflows.
17. Return DRAFT/HOLD-FOR-SOL. Do not merge/start production OOS.

## Development acceptance tests

Mandatory:

- all exact development SHAs replay;
- 110/110 frozen structural separators, zero false positives;
- 101 source-supported direct/proxy questioner cases resolve;
- 9 unresolved remain unresolved and structurally isolate spans;
- 10/10 source-clean calls produce non-empty full-call reconstruction;
- six conflicted calls fail only expected source identity/conflict class;
- AAPL exact 7/26/68;
- AAPL mutated SHA fail closed;
- roleless SCCO/COF management can be supported only from replayable same-revision roster/title text;
- ARRY/CTRE role conflicts refused;
- exact role-equivalence map has no open-ended aliases;
- accepted unsupported 0; cross-event 0; accepted replay 100%;
- no ticker/provider branch/new store/model path;
- production revision gate remains AAPL-only.

## Holdout acceptance

The holdout identities are immutable ranks 17–24 already frozen. Bodies remain unopened until implementation freeze.

Source-adjudication classification vocabulary:

- `QNA_SOURCE_CLEAN`
- `QNA_SOURCE_CONFLICTED`
- `NO_QA_ADMISSION`
- `SOURCE_REVISION_MISMATCH`

No slot replacement. At least 6/8 must be source-clean or the holdout is underpowered and the wave stops. When adequately powered, compiler success is required on **every** clean slot, not merely six.

## Proof owed

Return:

- branch/PR, pickup/base, exact final head;
- current-main collision receipt;
- changed files + necessity;
- RED evidence;
- AAPL 7/26/68 + mutated SHA;
- 16-call dev matrix against frozen adjudication;
- exact implementation-freeze SHA/timestamp;
- proof holdout bodies were unopened before that freeze;
- source-only holdout adjudication receipt SHA/artifact created before compiler output;
- exact 8-slot holdout matrix + power ruling + compiler score;
- proof zero code changes after holdout unseal;
- hard-safety totals;
- GOOGL known-falsifier regression;
- hosted CI/fences exact-head;
- confirmation production acceptance remains AAPL-only;
- final classification `BUILT_NOT_PROVEN` or named falsifier/blocker.

## Stop conditions

Stop without rescue if:

- accepted source law collides;
- any frozen revision SHA moves;
- method requires ticker/provider-specific logic;
- respondent/questioner identity needs external or guessed knowledge;
- dual respondent evidence cannot be backward-safe;
- AAPL 7/26/68 changes;
- any development source-clean call fails;
- separator precision/recall misses;
- holdout is opened before implementation freeze;
- holdout source adjudication is not frozen before compiler output;
- holdout has <6 source-clean slots;
- any clean holdout slot fails;
- any code change occurs after holdout unseal;
- production issuer/admission/publication changes appear necessary;
- CAT/BAC/SNOW inspection would be required.

## Continuation

TFG-1 does not close E3-C and cannot unlock E3-P. If Sol accepts TFG-1, the next operation is a **fresh pre-registered production OOS selection** on an untouched current event, with full E3 source completeness + canonical workspace + real Terminal proof. Only that successor OOS pass may close parent E3-C and make E3-P eligible.
