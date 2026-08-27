# TFG-0 R1 — Boundary, proxy-identity, role-equivalence and holdout scoring amendment

**Operation:** `tfg0-transcript-format-census-20260827-v1`  
**Authority:** Sol architecture amendment after the frozen 16-call development adjudication  
**Amends:** `TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_ARCHITECTURE_FREEZE_2026-08-27.md` §§4–6, 9–10 and the TFG-1 holdout scoring law where inconsistent  
**Runtime effect:** none  

This amendment is frozen **before any of the eight TFG-1 holdout bodies are opened**. It replaces two assumptions that the first TFG-0 draft could not know before the source-only development adjudication: (a) every real question handoff would have the same named person in the Operator cue and structured next-speaker field, and (b) `>=12/16 non-empty` was a lawful development bar.

Canonical measurement receipt: `tfg0_development_boundary_identity_adjudication.json`.

## 1. Measured development gold

Across the 16 already-open, exact-SHA development revisions:

- **110** real source-level analyst question handoffs;
- **95** direct Operator-name → immediate next-speaker matches;
- **6** explicit full-name proxy handoffs where the next speaker identifies themselves as `on for` / `sitting in for` the Operator-named principal;
- therefore **101** source-supported questioner handoffs under the law below;
- **9** real Q&A handoffs with insufficient/conflicting questioner identity;
- **2** calls with explicit management-role conflicts (`ARRY`, `CTRE`);
- exactly **10** calls are independently source-clean for the current all-or-nothing full-call reconstruction contract.

The earlier `>=12/16 non-empty` bar is therefore rejected: it exceeds the independently adjudicated source-clean ceiling and would pressure a worker to guess identities or introduce partial publication merely to satisfy a number.

## 2. Structural separator is not the same thing as mintable questioner identity

A real Q&A handoff can be structurally certain while its questioner identity is not canonicalizable. TFG-1 must separate those concepts.

### 2.1 Structural question separator

A structural separator exists when the same transcript revision contains an Operator/housekeeping handoff that is unambiguously question-bearing and is immediately followed by a non-housekeeping source turn. Opening prepared-speaker handoffs, generic queue instructions and closing returns are not separators.

Every one of the 110 adjudicated development handoffs is a structural separator.

A separator is load-bearing even when identity later refuses: it must divide adjacent exchange windows so an unresolved analyst's text cannot be merged into the prior or next accepted exchange.

### 2.2 Direct questioner

Direct source-supported questioner:

1. Operator handoff uniquely names X; and
2. the immediate next non-housekeeping structured speaker normalizes exactly to X under whitespace/case/honorific normalization only.

No edit distance, typo correction, nickname map or initials expansion.

### 2.3 Explicit proxy questioner

If the Operator names principal X but the immediate next structured speaker is full-name Y, Y is source-supported only when Y's **first source utterance** explicitly binds Y as `on for`, `sitting in for`, or an equivalent unambiguous on-behalf relation to X.

Then:

- canonical questioner `name = Y`;
- Operator-supplied affiliation of X **does not transfer automatically** to Y;
- affiliation stays `unresolved` unless the same handoff/utterance directly supports Y's affiliation.

This is deterministic transcript-local evidence, not fuzzy person resolution.

Development examples frozen in the adjudication receipt include Josh Fessler for Ghansham Panjabi, Robin Hanlon for Juan Sanabria, Lida Chen for Ben Chaiken, Ryan Payne for Jeff Rulis, Megan Lynch for Kelly Motta, and Andre Adams for Colin Rusch.

### 2.4 Unresolved separator

If the handoff is structurally real but the next-source identity cannot satisfy direct or explicit-full-name-proxy law, it is **separator-only** and cannot mint a canonical exchange.

Examples include structured `Speaker N` placeholders with only a first-name self-introduction, one-character name disagreements, a different named speaker with no proxy statement, and garbled Operator identity.

TFG-1 must preserve a typed refusal for these cases. It must not:

- infer a surname;
- edit-distance two names into equality;
- borrow the Operator principal's name as the actual speaker;
- silently drop the separator and merge spans across it.

The canonical publication behavior remains fail-closed/all-or-nothing for this method-hardening wave. TFG-1 does **not** gain authority to publish a partial call merely because it can structurally isolate an unresolved exchange.

## 3. Development acceptance law — evidence-conditioned, not arbitrary call count

TFG-1 development gates are now:

1. exact SHA replay for all 16 frozen revisions;
2. structural separator precision **100%** against the frozen adjudication: all 110 true handoffs recovered and zero opening/queue/closing false positives;
3. direct/proxy questioner law: all 101 source-supported handoffs resolve under the frozen rule;
4. all 9 unresolved handoffs remain separator-only/refused and do not contaminate adjacent windows;
5. **all 10 source-clean calls** produce non-empty deterministic full-call reconstruction through one generic path;
6. the remaining six development calls may fail only for the frozen source-identity / source-conflict conditions; none may fail because of terminal cue dialect (`go ahead`, `line open/live`, `proceed`, etc.);
7. AAPL remains exactly 7 exchanges / 26 management answer turns / 68 replay spans;
8. accepted unsupported = 0, cross-event contamination = 0, accepted span replay = 100%;
9. no ticker/issuer/provider branch.

The ten source-clean calls are frozen in `tfg0_development_boundary_identity_adjudication.json`; the builder may not redefine the set after observing implementation output.

## 4. Closed role-equivalence law

Role normalization exists **only for comparing two explicit same-revision source values**. It never invents a role.

### 4.1 Closed abbreviation families

Exactly these V1 equivalences are permitted:

- `CEO` ↔ `Chief Executive Officer`
- `CFO` ↔ `Chief Financial Officer`
- `COO` ↔ `Chief Operating Officer`

There is **no `etc.`** and no `CIO` abbreviation family. `Chief Investment Officer` is not treated as `Chief Information Officer` and neither is inferred from `CIO`.

### 4.2 Compound source titles

For comparison, a replayed roster/title declaration may be split only on explicit title separators (comma, semicolon, slash, or conjunction `and`).

A non-abbreviated segment role is compatible only with an exact normalized title component. A closed C-suite abbreviation is compatible only with its exact family component.

Examples:

- segment `CEO` vs roster `Chairman and Chief Executive Officer` → compatible;
- segment `CFO` vs roster `Vice President of Finance, Treasurer, and CFO` → compatible;
- segment `CFO` vs roster `Chief Investment Officer` → conflict;
- segment `President` vs roster `President and Chief Operating Officer` → compatible;
- segment `Managing Director` vs roster `Managing Director` → compatible.

If explicit same-revision role evidence is incompatible, fail `management_identity_conflict`. Do not select a preferred source field.

Publication string law is unchanged:

- compatible nonblank answer-segment role → preserve that source role string;
- blank answer-segment role + replayable roster/title support → preserve the normalized **source title phrase**, not a generated abbreviation or generic `Management`.

## 5. TFG-1 holdout law — source adjudication before compiler output

The eight frozen holdout identities in `tfg1_transcript_format_holdout_selection.json` remain unopened and irreplaceable.

After development gates are green:

1. freeze the exact TFG-1 implementation head SHA;
2. only then open the eight exact holdout revisions and byte-replay their frozen SHAs;
3. **before running the compiler on any holdout body**, create and freeze a source-only `tfg1.holdout_source_adjudication.v1` receipt using the same R1 rubric:
   - real question separators;
   - direct / explicit-full-name-proxy / unresolved questioner state;
   - same-revision respondent role/title support and explicit conflicts;
   - per-slot `QNA_SOURCE_CLEAN`, `QNA_SOURCE_CONFLICTED`, `NO_QA_ADMISSION`, or `SOURCE_REVISION_MISMATCH`;
4. no holdout slot may be replaced, skipped or re-ranked;
5. if fewer than **6 of 8** frozen slots are `QNA_SOURCE_CLEAN`, stop as `INSUFFICIENT_HOLDOUT_POWER`; do not substitute rank 25+ or another issuer;
6. otherwise run the already-frozen compiler **once** on the same eight revisions;
7. every `QNA_SOURCE_CLEAN` slot must produce non-empty deterministic full-call reconstruction;
8. every `QNA_SOURCE_CONFLICTED` slot must preserve all structural separators and fail only for the pre-adjudicated identity/conflict reason, never cue-format dependence;
9. every `NO_QA_ADMISSION` slot must produce no false Q&A boundary;
10. `SOURCE_REVISION_MISMATCH` remains a hard source failure and is not replaced;
11. holdout structural-boundary precision/recall must be 100% against the frozen source-only adjudication;
12. hard safety gates remain accepted unsupported 0, cross-event 0, accepted replay 100%;
13. **no code change is permitted after holdout bodies are opened**, regardless of whether the compiler has run yet. A miss returns to Sol under a new method-hardening operation.

This replaces the earlier bare `>=6/8 non-empty` outcome bar. Six of eight is now the **minimum source-clean power requirement**, while compiler success is required on **all** source-clean holdout slots.

## 6. What this changes and does not change

Changes:

- terminal phrases lose all boundary authority;
- explicit full-name proxy relation becomes a closed transcript-local questioner path;
- unresolved real handoffs become separator-only typed refusals;
- development/holdout scoring is conditioned on pre-adjudicated source truth rather than an impossible arbitrary success count;
- role-equivalence vocabulary is now exact and closed.

Does not change:

- `qa_exchange.v1` source-supported identity requirement;
- AAPL production acceptance or immutable AAPL objects;
- the optional roster-evidence amendment already frozen for future TFG-validated revisions;
- production revision admission (still AAPL-only during TFG-1);
- no-partial-publication law for TFG-1;
- source clocks, rights, event identity, publisher, Terminal production contract, Prophet/FIF boundaries;
- GOOGL's status as known falsifier only;
- CAT/BAC/SNOW embargo;
- E3-P lock.
