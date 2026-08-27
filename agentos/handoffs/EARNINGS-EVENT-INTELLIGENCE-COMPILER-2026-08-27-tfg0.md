---
program: earnings-intelligence
workstream: EARNINGS-EVENT-INTELLIGENCE-COMPILER
date: 2026-08-27
wave: TFG-0
state: SPEC_ONLY_PENDING_SOL_ACCEPTANCE
operation_key: tfg0-transcript-format-census-20260827-v1
carrier: macro#6521
---

# E3 / TFG-0 — Transcript Format Generalization handoff

## Why this exists

The frozen GOOGL E3-C out-of-sample attempt truthfully refused on transcript source format. Sol ruled that GOOGL is spent as future OOS acceptance evidence: do not tune on GOOGL and retest it as OOS, and do not immediately switch the failed carrier to CAT/BAC/SNOW.

TFG-0 therefore pre-registered a development census before inspecting any additional transcript body, measured the existing deterministic Q&A parser across independently selected held formats, and froze the next repair method without modifying runtime code.

## Exact TFG-0 carrier

- PR: Macro #6521
- operation: `tfg0-transcript-format-census-20260827-v1`
- pickup main: `5d07658b899d2d3457dfeeccbc0a91c280f5bc1f`
- pre-registration-before-body-inspection commit: `05e4ddde16e9cd94c79ce3dd21a8a25db865da51`
- final research head at time of this handoff: branch continues; re-read PR exact head before acceptance
- completion if accepted: `SPEC_ONLY`

## Measured result

Production transcript index snapshot:

- schema `mastermind.tx-index/v1`
- generated_at `2026-08-27T00:17:17.252644+00:00`
- 28,741 bodies / 3,572 symbols
- exact index SHA-256 `58f15ff0540f2aa0228348dda6f0ee34b26ef6d3227582fe59793fd43e0af496`

TFG eligible held revisions under the frozen law: **2,909**.

Development corpus:

- deterministic hash-selected first 16 revisions;
- AAPL, GOOGL/GOOG, CAT, BAC and SNOW excluded;
- 16/16 byte replay;
- 0 source revision mismatch;
- zero model calls;
- zero reserved OOS body inspection.

Unchanged deterministic compiler:

- **0 / 16 successful**;
- 11 `operator_intro_identity_unparsed`;
- 5 `zero_qa_boundaries`.

This proves the GOOGL failure is a systemic source-format coverage gap, not an isolated ticker/vendor exception.

Across the exact 16 bodies:

- 1,524 segments;
- 672 blank-role segments (44.1%);
- every call contains blank role;
- SCCO and COF have only `Operator` + blank role vocabulary;
- same-transcript opening rosters provide replayable management title evidence for roleless structured speakers;
- at least ARRY and CTRE contain direct conflicts between segment `role` metadata and explicit title text.

## Architecture ruling

TFG-0 selects **transcript-local source evidence normalization**.

Boundary law:

- terminal phrases (`go ahead`, `line open/live`, `proceed`) have zero primary authority;
- admit Q&A only through a named Operator handoff that binds to the next non-housekeeping source speaker;
- generic Q&A instructions, presentation handoffs and closing management returns are not boundaries.

Questioner law:

- name anchored to the verified next source speaker + same-person Operator clause;
- affiliation parsed only inside the admitted handoff clause and may remain existing `unresolved`;
- abbreviation-safe; no external people lookup.

Respondent law:

- source evidence may be segment role, same-revision transcript-local title declaration, or compatible combination;
- source-native aliasing may strip honorifics / use a unique contiguous multi-token speaker-name prefix only;
- no nickname/fuzzy/cross-call inference;
- incompatible role evidence -> `management_identity_conflict`;
- missing role evidence -> existing `management_identity_insufficient`;
- accepted identity remains `source_supported`.

Canonical evidence law:

- legacy respondent shape remains valid;
- roster-derived accepted role requires optional nested `qa_respondent_identity_evidence.v1` with replayable same-revision `role_source_spans`;
- no nullable role, generic `Management`, new top-level workspace key, new Q&A store or builder-invented `qa_exchange.v2`.

## TFG-1 format holdout — EMBARGOED

A separate eight-revision format holdout is frozen by metadata/SHA only as ranks 17-24 of the same deterministic ordering.

Receipt: `research/earnings_intelligence/e3/tfg1_transcript_format_holdout_selection.json`.

**Bodies inspected: 0.**

Do not open these bodies until a future TFG-1 implementation head is frozen and the development suite is green. If the holdout fails its frozen bar, do not patch the same implementation carrier after seeing it and then call it unseen validation.

## Frozen TFG-1 breadth bars

Before implementation:

- AAPL oracle stays exactly 7 exchanges / 26 management answer turns / 68 replay spans;
- current AAPL-only production revision admission stays closed;
- development corpus must reach >=12/16 non-empty through one generic deterministic method;
- valid Q&A may not fail merely because terminal cue dialect lacks `go ahead`;
- any remaining development failure must be source identity/conflict/replay, not phrase-format failure;
- hard gates: accepted unsupported 0, cross-event 0, 100% accepted replay.

After implementation head freeze:

- open exact eight holdout revisions once;
- >=6/8 non-empty;
- no old literal-terminal-cue failure class;
- hard gates remain green;
- no post-holdout tuning on that carrier.

Then run GOOGL only as a known regression. It cannot serve as OOS acceptance.

## Durable evidence

- dev selection run/job/artifact: `33042834588` / `98420076116` / `9634504377`; artifact SHA `33cfa64643deb70b3690d78c33543898b3fcf1d49c2f1fdcb3e321f3b29608e5`
- unchanged-compiler census artifact: `9634565138`; SHA `8e14d491fd92f596fcd7c89656a8b4540d8339857ed3b853ad6456ad6c29c4a7`
- structural census run/job/artifact: `33043092699` / `98420881749` / `9634595572`; SHA `688f7c70bb97c31cf35227c317e7516c89f3ebf0e0bbb17cf994d9e121df5bf5`
- holdout freeze run/job/artifact: `33043554816` / `98422311316` / `9634756392`; SHA `464a65d696dc97ee82780c857924da72f3757b12f5f86c196470e943b456675f`

Temporary proof workflows were removed after evidence capture. TFG-0 final PR carries records/research only.

## Collision / current state

At TFG-0 pickup, E3-C refusal PR #6497 was concurrently being repaired under Sol review. TFG-0 deliberately did **not** edit `agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md` so it could not clobber that carrier.

Before accepting #6521, reconcile #6497 and current `main`. Once #6497's refusal records land, update the E3 workstream to link TFG-0 as the method-hardening architecture and TFG-1 as the exact next implementation wave.

## Do not redo / do not leak

- do not reopen GOOGL as OOS acceptance;
- do not inspect CAT/BAC/SNOW in TFG development;
- do not inspect the eight TFG-1 holdout bodies before implementation freeze;
- do not source-shop another GOOGL provider to rescue the failed test;
- do not weaken source-supported respondent identity;
- do not create another transcript/Q&A/identity/publication plane;
- do not start E3-P.

## Exact next action

After #6497 and TFG-0 are Sol-accepted and reconciled, commission `TFG1_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-27.md` as one bounded Macro implementation. Stop after held-development + unseen-format validation and return to Sol. Fresh second-issuer production/OOS selection is later.
