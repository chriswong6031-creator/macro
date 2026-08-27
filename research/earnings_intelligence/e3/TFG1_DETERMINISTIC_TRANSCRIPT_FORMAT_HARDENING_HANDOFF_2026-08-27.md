# TFG-1 — Deterministic transcript-format hardening handoff

**Status:** FUTURE COMMISSION PACKET — do not start until TFG-0 is Sol-accepted/landed and the E3-C refusal carrier is reconciled  
**Preferred operator:** one strong frontier coding worker for a bounded Macro-only implementation  
**Expected completion class:** `BUILT_NOT_PROVEN` for broader production coverage; method capability must be proven on held development + unseen format holdout  

## Observable mission

Make the existing deterministic Q&A reconstruction/canonicalization path correctly handle multiple held transcript formats — including roleless-but-source-supported management — while preserving AAPL exactly and refusing ambiguous identity, then prove the frozen implementation on the eight pre-selected unseen format revisions without opening those bodies before code freeze.

## Why it matters

The GOOGL E3-C falsifier exposed source-format dependence. TFG-0 then measured the unchanged compiler against 16 independently selected held calls: **0/16 succeeded**. Eleven failed after literal `go ahead` admitted a false pre-Q boundary; five had no literal `go ahead` boundary at all. This is the method bottleneck preventing a truthful fresh OOS production proof.

TFG-1 fixes the deterministic method only. It must not rescue GOOGL by special case, broaden production issuer registration or pre-consume the later production OOS event.

## Authority / precedence

At pickup, read current `main` and apply the newest accepted versions in this order:

1. `research/earnings_intelligence/e3/TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_ARCHITECTURE_FREEZE_2026-08-27.md`
2. `research/earnings_intelligence/e3/tfg0_transcript_format_census_receipt.json`
3. `research/earnings_intelligence/e3/TFG1_TRANSCRIPT_FORMAT_HOLDOUT_PREREG_2026-08-27.md`
4. `research/earnings_intelligence/e3/tfg1_transcript_format_holdout_selection.json`
5. `research/earnings_intelligence/e3/TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_PREREG_2026-08-27.md`
6. `research/earnings_intelligence/e3/E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`
7. the landed E3-C GOOGL refusal receipt / current `WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER` state.

If a newer accepted E3/Q&A/source-identity law materially collides, STOP and return to Sol. Retrieved comments or PR prose do not outrank accepted source law.

## Verified starting state

Re-pin at pickup; do not assume these SHAs remain current.

TFG-0 measured:

- production transcript index snapshot: 28,741 bodies / 3,572 symbols;
- eligible TFG universe: 2,909 revisions;
- development corpus: 16 exact revisions, 16/16 byte replay;
- unchanged parser: 0/16 success;
- failures: 11 `operator_intro_identity_unparsed`, 5 `zero_qa_boundaries`;
- blank role segments: 672 / 1,524 (44.1%);
- SCCO and COF development calls expose only `Operator` + blank role vocabulary;
- transcript-local participant/title evidence exists for roleless speakers;
- ARRY and CTRE demonstrate role metadata can conflict with explicit transcript title text.

Existing AAPL production oracle remains:

- transcript SHA `a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f`;
- 7 exchanges;
- 26 management answer turns;
- 68 replay spans.

Current production acceptance is still AAPL-revision-gated. TFG-1 must **not widen that production revision admission**.

## Exact scope

Repository: `mastermindx-market-intelligence/macro` only.

Expected ownership surface:

- `engine/company_intelligence/qa_reconstruction.py`
- `engine/company_intelligence/qa_exchange.py`
- existing Q&A reconstruction/exchange tests
- one new focused TFG-1 test module
- bounded exact-source fixtures or temporary read-only proof workflow only if necessary for held-source verification; temporary proof workflow must be removed before final PR return.

A small private helper under `engine/company_intelligence/` is allowed only if it is clearly an implementation detail of the existing Q&A compiler and does not become a second identity/source registry. Prefer keeping normalization with the existing Q&A modules unless separation materially improves auditability.

## Protected / no-edit surfaces

Do not edit or widen:

- `event_workspace.production_registry()`;
- Alphabet/GOOGL issuer registration;
- `scripts/refresh_event_workspaces.py` production coverage;
- accepted AAPL-only production revision admission;
- Terminal repository/UI;
- E3-P;
- FIF, Prophet, scoring, sentiment, beat/miss or model routing;
- source acquisition/provider selection;
- Agent OS lifecycle/control planes.

Do not inspect CAT/BAC/SNOW transcript bodies.

## Complete machine journey

### Development path

```text
exact held transcript revision
→ deterministic source-evidence normalization
→ verified named Operator handoffs
→ deterministic question/answer reconstruction
→ deterministic source-supported respondent identity
→ canonical qa_exchange validation in test/shadow context
→ non-empty or typed fail-closed result
```

### Unseen-format holdout path

```text
implementation head frozen + dev tests green
→ only then open 8 frozen holdout revisions
→ byte replay exact advertised SHA
→ run frozen compiler once
→ record pass/refusal + safety evidence
→ STOP; no tuning after viewing holdout
```

### GOOGL regression path

After the implementation head and holdout result are frozen, rerun exact GOOGL Q2 only as a known regression. It cannot be an OOS pass.

## Deterministic method

No model calls.

### Boundary

Replace literal-terminal-cue authority with named-handoff evidence:

- next non-housekeeping source speaker is the anchor;
- Operator clause must bind uniquely to that exact speaker;
- first Q&A boundary requires explicit question-bearing handoff syntax;
- after Q&A begins, a named continuation handoff such as `move on to <speaker>` may qualify;
- generic queue/Q&A instructions and prepared/closing handoffs do not qualify;
- `go ahead`, `line open/live`, `proceed` are diagnostics only.

### Questioner

- questioner name = verified next source speaker + same-person Operator reference;
- affiliation parsed only inside the admitted handoff clause;
- abbreviation-safe (`J.P.`, `D.A.`, `B.` etc. cannot be truncated as sentence ends);
- affiliation may remain existing `unresolved`.

### Respondent role

Use only the same transcript revision:

- segment role;
- transcript-local participant/title declaration;
- or compatible combination.

Source-native aliasing may strip honorifics and use a unique contiguous multi-token prefix of a structured speaker name. No nickname dictionary, edit distance, external directory or cross-call role carry-forward.

Use a closed role-family equivalence map only to compare explicit source values (`CEO` ≈ `Chief Executive Officer`, etc.). Never use that map to create a role not present in source.

Conflict => `management_identity_conflict` refusal. Missing support => existing `management_identity_insufficient` refusal.

## Canonical respondent identity evidence

Preserve legacy accepted respondent shape for existing objects:

```text
{name, role, identity_state, span_indexes}
```

For a respondent whose role comes from transcript-local roster text rather than its answer segment role, add the frozen optional nested evidence:

```text
identity_evidence: {
  schema: "qa_respondent_identity_evidence.v1",
  method: "transcript_roster",
  role_source_spans: [source_span.v1, ...]
}
```

Requirements:

- roster-derived accepted roles require at least one exact replayable role source span from the same document revision;
- validator independently replays it and verifies the speaker/title relationship;
- accepted `identity_state` remains `source_supported`;
- legacy four-key respondent remains valid;
- no nullable `role`, no generic `Management`, no `qa_exchange.v2` on builder judgment;
- if backward-safe dual-shape validation cannot be implemented without breaking immutable AAPL reads, STOP and return to Sol.

TFG-1 may implement this Macro contract because production admission remains AAPL-only. Terminal support belongs to the later fresh-OOS publication vertical when an extended respondent is actually going to be published to a real consumer.

## Data / identity / time / null / correction

- every result is bound to exact `document_id + document_sha256`;
- changed SHA invalidates all transient boundary/roster evidence and reconstruction;
- no identity/title evidence crosses revisions;
- transcript `source_available_at` semantics remain unchanged; unknown stays null/unknown;
- roster/title evidence is not a new durable person registry;
- affiliation may be unresolved; accepted respondent role may not;
- cross-event/ticker identity rules remain unchanged.

## TDD / ordered implementation sequence

1. Re-pin current Macro main, current E3/TFG laws, open overlapping PRs. Stop on material collision.
2. Write RED discriminators before production changes:
   - pre-Q `go ahead` presentation handoff must not become Q&A;
   - valid named `line open/live`, `may proceed`, `please proceed`, no-terminal-cue and post-Q `move on to` handoffs must be recognized generically;
   - Operator handoff name must equal next non-housekeeping source speaker;
   - abbreviation-safe affiliation examples;
   - roleless management + exact transcript-local title declaration resolves;
   - incompatible segment role vs roster title refuses;
   - no role evidence refuses;
   - external/nickname/fuzzy inference mutant is killed;
   - role-evidence revision/span mismatch is killed.
3. Implement the smallest deterministic source-evidence normalization.
4. Implement boundary + questioner parsing without ticker/provider branches.
5. Implement source-local role resolution/conflict law.
6. Implement optional nested respondent identity evidence and exact validator replay.
7. Verify AAPL remains exactly 7 / 26 / 68 and changed AAPL SHA still refuses inherited accepted Q&A.
8. Run all 16 development revisions under the frozen bar:
   - >=12/16 non-empty;
   - no valid call fails merely due terminal cue dialect;
   - any remainder is identity/conflict/replay refusal;
   - hard safety green.
9. Freeze the implementation head. Record its SHA. Do not inspect holdout before this point.
10. Open and run the exact 8 holdout revisions from `tfg1_transcript_format_holdout_selection.json` once:
    - >=6/8 non-empty;
    - no old literal-cue-format failure;
    - hard safety green.
11. **If holdout misses the frozen bar: STOP. Do not patch the same carrier after seeing holdout and then call it unseen validation.** Return to Sol with the exact falsifier.
12. If holdout passes, run GOOGL known-falsifier regression without changing code.
13. Run focused + planner-selected hosted CI. Remove any temporary proof workflow before final return.
14. Keep PR DRAFT/HOLD-FOR-SOL; do not widen production revision admission and do not merge.

## Discriminating acceptance tests

Mandatory:

- AAPL exact 7 exchanges / 26 management turns / 68 replay spans;
- AAPL mutated SHA fail-closed unchanged;
- no ticker/issuer constants in Q&A format method;
- false pre-Q presentation handoff rejected;
- questioner/next-speaker mismatch rejected;
- roleless respondent with exact roster support accepted with replayable `qa_respondent_identity_evidence.v1`;
- roster evidence from wrong document/revision rejected;
- unsupported/fuzzy/external role inference rejected;
- explicit role conflict rejected;
- exact source spans unique/replayable;
- accepted unsupported = 0;
- cross-event contamination = 0;
- 100% accepted span replay;
- no new store/schema plane/publisher/model route;
- production accepted-revision gate remains AAPL-only.

Development corpus: >=12/16 non-empty.

Unseen holdout: >=6/8 non-empty after implementation head frozen, with no post-holdout repair.

## Proof owed

TFG-1 does **not** owe production publication or browser proof because it is deliberately development-unarmed. It owes real held-source proof:

- exact development revision SHAs;
- exact frozen implementation SHA;
- exact eight holdout revision SHAs + byte replay;
- per-call non-empty/refusal matrix;
- hard safety matrix;
- GOOGL regression result;
- hosted CI on exact final head.

Do not call TFG-1 `PROVEN_LIVE`. A clean method-hardening return is `BUILT_NOT_PROVEN` for broader production coverage and eligible for Sol to commission the fresh OOS publication wave.

## Failure / stop conditions

STOP and return without rescue when:

- current accepted source law materially collides;
- held revision SHA differs from frozen corpus/holdout identity;
- method requires ticker/provider-specific parsing;
- respondent role requires external/guessed person knowledge;
- nested identity evidence cannot remain backward-safe;
- AAPL changes from 7/26/68;
- development bar misses;
- holdout bar misses;
- holdout is accidentally inspected before implementation freeze;
- production issuer/admission/publication changes seem necessary;
- CAT/BAC/SNOW would need to be inspected.

## Required Sol return packet

Return on the one implementation carrier:

- branch, PR, pickup/base SHA, exact final head SHA;
- current-main movement/collision receipt;
- changed-file list and why every file is necessary;
- RED tests and observed failures before implementation;
- focused + full selected GREEN commands/results;
- AAPL exact 7/26/68 + mutated-SHA result;
- 16-call development matrix with exact revision SHA, non-empty/refusal and failure code;
- implementation-freeze head SHA and timestamp **before holdout body access**;
- 8-call holdout matrix, byte replay, >=6/8 ruling and proof no code change followed holdout observation;
- hard safety totals;
- GOOGL known-falsifier regression result;
- hosted CI/fences on exact final head;
- confirmation production accepted-revision gate remained AAPL-only;
- discovered conflicts/limitations;
- final worker classification: `BUILT_NOT_PROVEN` or named falsifier/blocker.

Do not start fresh OOS selection, production publication or E3-P. Sol owns that continuation.
