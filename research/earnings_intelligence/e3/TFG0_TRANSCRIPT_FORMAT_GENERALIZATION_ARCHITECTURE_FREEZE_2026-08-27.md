# TFG-0 — Transcript Format Generalization architecture freeze

**Operation:** `tfg0-transcript-format-census-20260827-v1`  
**Authority:** Chairman continuation + Sol E3-C REVIEW_RETURN  
**Outcome:** freeze the repair method after a deterministic multi-source census, before TFG-1 implementation  
**Capability state:** `SPEC_ONLY` after this freeze lands; no production capability is added here

## 1. Why this wave exists

GOOGL Q2 FY2026 falsified the AAPL-calibrated deterministic Q&A parser on source format rather than ticker identity. TFG-0 was created so the repair would not be fitted directly to GOOGL and then mislabeled an out-of-sample pass.

Before opening any new transcript body, TFG-0 committed its corpus law. The production `mastermind.tx-index/v1` then yielded 2,909 eligible held revisions. A deterministic hash ordering selected 16 development revisions while excluding AAPL, GOOGL/GOOG, CAT, BAC and SNOW. All 16 byte-replayed to the advertised revision SHA. No model call occurred.

The unchanged current compiler failed **16 / 16**:

- `operator_intro_identity_unparsed`: **11 / 16**;
- `zero_qa_boundaries`: **5 / 16**;
- successful non-empty reconstruction: **0 / 16**.

This is a systemic source-format coverage gap, not a GOOGL-only exception.

## 2. Measured source-format facts

### 2.1 Literal terminal cues cannot be the boundary law

The 16-call corpus contains real analyst handoffs expressed through multiple source forms, including:

- `go ahead`;
- `your line is open / live`;
- `you may proceed`;
- `please proceed`;
- `your question, please`;
- `we'll move on to <name>` / equivalent named handoff after Q&A has begun.

At the same time, conference-open housekeeping frequently contains both the word `question` and a presentation/IR `go ahead`. Ten development calls caused the current parser to select segment 0 as its first `go ahead` boundary. Five other calls had no qualifying `go ahead` boundary at all.

**Ruling:** terminal cue text is optional corroboration only. It is never the primary boundary predicate.

### 2.2 Segment `role` is not a complete identity authority

Across 1,524 exact held segments, 672 have blank `role` (44.1%). Every one of the 16 calls contains blank-role segments. Two calls — SCCO Q2 and COF Q2 — have no non-housekeeping role vocabulary at all: only `Operator` and blank.

The same held transcript often contains better source evidence in the opening roster. A conservative exact-speaker-name scan already found replayable title declarations for roleless speakers in six of the 16 calls, including examples such as:

- OCSL: roleless house speakers named in the opening roster with explicit titles;
- TRVI: roleless development/commercial executives named with explicit titles;
- FANG: a roleless house speaker explicitly introduced with a title;
- COF: all management segment roles are blank while the opening text explicitly names the CEO and CFO.

The exact-name scan is deliberately conservative and misses source-native aliases such as shortened or multi-surname forms.

### 2.3 Segment role metadata can conflict with the transcript text

At least two development calls contain direct source conflicts:

- ARRY: transcript text identifies Keith Jennings as CFO and Neil Manning as President/COO while segment role metadata labels their speech CEO and CFO respectively;
- CTRE: transcript text identifies James Callister as Chief Investment Officer while segment metadata labels his speech CFO.

**Ruling:** a non-empty segment role is evidence, not unquestioned authority. Explicit incompatible source evidence must fail closed rather than choosing whichever field is convenient.

## 3. Selected architecture — transcript-local source evidence normalization

TFG-1 shall add one **transient deterministic normalization stage inside the existing Q&A compiler path**. It is not a durable object, store, registry, model plane or second transcript representation.

Conceptually:

```text
exact held transcript revision
        │
        ├─ structured segment speaker / role fields
        ├─ replayable transcript-local participant/title declarations
        └─ Operator handoff text
        │
        ▼
transient source-evidence normalization
        │
        ├─ verified question-boundary candidates
        ├─ questioner identity + affiliation state
        └─ respondent role evidence / conflict / unresolved
        │
        ▼
existing deterministic exchange reconstruction
        │
        ▼
existing canonical qa_exchange path
```

No model call participates in this path.

## 4. Boundary invariant

A Q&A boundary is admitted only by **positive named-handoff evidence**, not by a terminal phrase.

For each Operator/housekeeping segment:

1. Resolve the next non-housekeeping source speaker.
2. Find a single handoff clause in the Operator text that binds to that exact source speaker.
3. Before Q&A is established, the clause must be explicitly question-bearing — for example a first/next/final question `from / comes from / is from`, or `take ... question from` construction.
4. After Q&A is established, a named continuation handoff such as `move on to <speaker>` may qualify if the next speaker matches and the target is not a house-side participant.
5. Generic Q&A instructions, queue instructions, prepared-speaker handoffs and closing returns to management are not boundaries even if they contain `question` or `go ahead`.
6. The verified next speaker becomes the source anchor for questioner-name validation. Do not discover a convenient analyst name and then search for a matching speaker later.

`go ahead`, `line open/live`, `proceed` and similar terminal text may be retained as diagnostics but have zero admission authority.

## 5. Questioner identity and affiliation

### 5.1 Name

Questioner name is source-supported only when:

- the structured next non-housekeeping segment has a non-empty speaker name; and
- the same person is uniquely referenced by the admitted Operator handoff clause.

Normalize whitespace/case/honorifics for comparison only. No external people directory and no fuzzy biography matching.

### 5.2 Affiliation

Parse affiliation only inside the admitted handoff clause, anchored after the verified questioner mention through source prepositions such as `with`, `from`, `of` or `at`.

Clause termination must be abbreviation-safe. `J.P. Morgan`, `D.A. Davidson` and `B. Riley` must not collapse at their internal periods. A grammatical shift to the next Operator control clause or the verified questioner's direct address ends the affiliation.

Affiliation may remain `unresolved`, matching the existing `qa_exchange.v1` law. A source-supported questioner name must not be dropped merely because affiliation is unavailable.

## 6. Respondent role resolution

### 6.1 Evidence classes

For a structured transcript speaker, TFG-1 may use only evidence from the **same exact held transcript revision**:

1. non-empty segment role attached to that speaker;
2. replayable transcript-local participant/title declaration adjacent to that same speaker name, normally in the pre-Q&A call roster;
3. both, if semantically compatible.

No external biography, issuer website, model inference or stale prior-quarter title may fill a role.

### 6.2 Source-native alias law

Name association is deterministic and document-local:

- exact normalized full speaker name is preferred;
- honorifics may be stripped;
- a contiguous multi-token prefix of the structured speaker name may be used only when it uniquely identifies exactly one structured speaker in that document;
- no edit-distance, nickname table, initials expansion or cross-document person resolver.

Thus a source-native multi-surname shortening can be supported when unique; `Dave` → `David` is **not** silently inferred.

### 6.3 Compatibility and conflict

Role/title abbreviations may be normalized into a closed comparison family only for conflict detection (`CEO` ↔ `Chief Executive Officer`, `CFO` ↔ `Chief Financial Officer`, `COO` ↔ `Chief Operating Officer`, etc.). This normalization does not grant a title that the source never states.

- segment role only, no conflict → source-supported;
- roster title only, uniquely replayable → source-supported;
- both and compatible → source-supported;
- incompatible evidence → fail the exchange as `management_identity_conflict`;
- no role/title evidence → existing `management_identity_insufficient` refusal.

When segment role is already non-empty and compatible, preserve the existing role string for AAPL/backward stability. When the segment role is blank and a roster title is the support, publish the normalized source title string derived from the replayed declaration; never replace it with generic `Management`.

## 7. Canonical evidence extension — no silent role invention

The present canonical respondent is:

```text
{name, role, identity_state, span_indexes}
```

and `identity_state` is `source_supported`. Terminal mirrors this closed shape. A roster-derived role therefore needs explicit canonical evidence; silently filling `role` from another segment would make the value harder to audit than the current AAPL objects.

TFG-1 shall add one **optional versioned nested respondent extension**, not a new workspace key or store:

```text
identity_evidence: {
  schema: "qa_respondent_identity_evidence.v1",
  method: "transcript_roster",
  role_source_spans: [source_span.v1, ...]
}
```

Rules:

- legacy four-key respondents remain valid and readable; immutable AAPL generations do not need migration;
- roster-derived accepted roles require the extended five-key respondent shape;
- `role_source_spans` must point to the same exact transcript document revision and replay the declaration supporting the respondent's role/title;
- the validator independently replays those spans and rechecks name/title compatibility;
- `identity_state` remains exactly `source_supported` for accepted respondents;
- unresolved/conflicting identity is not published as an accepted respondent.

Terminal's verified reader must accept exactly the frozen legacy shape or the frozen extended shape. The current Q&A renderer need not display this evidence field; it remains source/audit support. No top-level `event_workspace` key is added and parent workspace schema stays `event_workspace.v1`.

If implementation review proves this optional nested extension cannot be made backward-safe without weakening immutable-generation reads, STOP and return to Sol. Do not silently make `role` nullable and do not invent `qa_exchange.v2` on builder judgment.

## 8. Revision / correction law

All normalization is document-revision scoped.

```text
same event_id + changed transcript SHA
→ discard prior transient roster/boundary evidence
→ rerun deterministic reconstruction
→ revalidate every respondent role source span
→ new revision-scoped exchange ids / workspace generation
```

No role evidence crosses revisions. No prior-quarter title carries forward. A changed source cannot inherit the old call's accepted Q&A.

## 9. Failure law

Preserve existing fail-closed behavior for TFG-1. This wave does **not** introduce partial-per-exchange publication semantics as a convenience.

Use existing typed failures where they remain truthful:

- `zero_qa_boundaries` — no verified named question handoff;
- `operator_intro_identity_unparsed` — handoff exists but unique source identity cannot be established;
- `operator_analyst_name_conflict` — Operator handoff and next source speaker disagree;
- `management_identity_insufficient` — respondent role/title cannot be source-supported;
- `span_replay_failed` — evidence does not replay.

Add only one new failure if necessary:

- `management_identity_conflict` — incompatible source role/title evidence for the same respondent.

Do not turn an ambiguous exchange into guessed structure to improve coverage.

## 10. TFG-1 development and holdout gates

### 10.1 Development corpus

TFG-1 may use the 16 already-inspected TFG-0 development revisions.

Baseline is 0/16 successful.

Before code is written, TFG-1 tests must freeze these bars:

- all 16 exact revision SHAs replay;
- **no valid Q&A call may fail solely because it lacks literal `go ahead`**;
- false pre-Q presentation/IR handoffs are never admitted as Q&A boundaries;
- at least **12 / 16** calls produce non-empty deterministic reconstruction through one generic path;
- remaining development failures, if any, must be typed source-identity/conflict failures rather than phrase-format failures;
- accepted unsupported = 0;
- cross-event contamination = 0;
- span replay = 100% of accepted;
- AAPL exact oracle remains 7 exchanges / 26 management answer turns / 68 replay spans;
- no ticker/issuer/source-provider branch in the reconstruction method.

The 12/16 bar is a pre-implementation breadth floor, not production authority. Failing it returns to Sol; the builder does not loosen the bar.

### 10.2 Eight-call unseen format holdout

Ranks 17–24 of the same deterministic eligibility ordering are frozen separately in `tfg1_transcript_format_holdout_selection.json`. Their bodies are embargoed until the TFG-1 implementation head is frozen and development tests are green.

After code freeze:

- byte replay all eight exact SHAs;
- run the frozen compiler once;
- at least **6 / 8** must produce non-empty deterministic reconstruction;
- all eight must avoid the old literal-cue failure class: any refusal must be a truthful source-identity/conflict/replay refusal, not `go ahead` dialect dependence;
- hard safety gates remain zero unsupported, zero cross-event, 100% accepted replay.

After holdout results are observed, no repair may be made on the same implementation carrier and then call those same eight an untouched pass. A failed holdout returns to Sol for a new method-hardening operation.

The eight-call holdout is method-format validation only. It does not unlock E3-P.

## 11. GOOGL disposition

GOOGL remains a permanent known falsifier, not an OOS acceptance set.

After the TFG-1 method is frozen, rerun the exact GOOGL Q2 revision only as a regression:

- segment 0 presentation/IR handoff must not be admitted as Q&A;
- real named analyst handoffs must be recognized by the generic boundary method;
- affiliation parsing must not absorb the terminal Operator sentence;
- any management role emitted must be replayably source-supported under the TFG-0 role law;
- if the held GOOGL body cannot source-support a respondent role even through transcript-local evidence, it must still fail honestly rather than invent a title.

GOOGL success is useful regression evidence but is **not** the fresh OOS proof.

## 12. Fresh OOS after TFG-1

Only after TFG-1 implementation + unseen format holdout are accepted may Sol pre-register a new E3 second-issuer production acceptance selection.

That later operation must:

- select an untouched current event before extraction;
- require the full E3 source-completeness bar;
- publish non-empty accepted Q&A through the frozen TFG method;
- reach canonical `event_workspace.v1` and real Terminal consumption;
- preserve all hard safety gates.

CAT/BAC/SNOW remain untouched by TFG-0 and are not automatically selected. The fresh selection law will decide the successor event before its output is inspected.

E3-P remains locked until that successor production OOS proof passes.

## 13. No-rebuild boundaries

TFG-1 must not create:

- another transcript store/provider registry;
- another Q&A/candidate database;
- ticker-specific extraction branches;
- external person/title inference;
- a second event/identity/publication plane;
- model routing for deterministic Q&A structure;
- scoring, sentiment, beat/miss, rank, size, gate, trade or Prophet authority;
- partial-publication semantics merely to pass the corpus;
- E3-P work.

## 14. What this freeze makes true

After this records-only architecture is accepted, Mastermind will know **how** to repair the source-format layer without contaminating its next OOS proof. It will not yet have broader production Q&A coverage.

TFG-0 completion classification: `SPEC_ONLY`.

Exact next capability operation: TFG-1 deterministic transcript-format hardening against the frozen development corpus, followed by the eight-call unseen format holdout and Sol return. Production/OOS publication remains a later operation.
