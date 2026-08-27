# TFG-0 — `qa_exchange.v1` respondent identity-evidence amendment

**Date:** 2026-08-27  
**Authority:** Sol architecture amendment after the pre-registered TFG-0 held-source census  
**Parent law amended:** `E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md` §7, respondent row only  
**Runtime effect of this record:** none  

## Why an explicit amendment is required

E3-0 §7 froze each `qa_exchange.v1.respondents[]` element as:

```text
{name, role, identity_state, span_indexes}
```

The live implementations are stricter still:

- Macro `engine/company_intelligence/qa_exchange.py` uses exact `RESPONDENT_KEYS = ("name", "role", "identity_state", "span_indexes")`;
- Terminal `terminal/lib/eventWorkspace.ts` uses an exact-key respondent normalizer with the same four-key shape.

Therefore a fifth nested field is **not** an open/additive compatibility assumption. Publishing it today would make the current Terminal reader reject the Q&A object. TFG-0 does not authorize such publication.

The TFG-0 census nevertheless established a new source-evidence need that E3-0 could not have specified from AAPL alone:

- segment `role` is blank on 44.1% of the 1,524 development segments;
- SCCO and COF publish no non-housekeeping role metadata at all;
- those same exact transcript revisions contain replayable participant/title declarations that source-support roleless management;
- ARRY and CTRE show that non-empty segment-role metadata can conflict with explicit transcript title text.

Silently copying a role from another segment into the four-key respondent would preserve the apparent schema while **hiding the actual evidence transformation**. Making `role` nullable or inventing `Management` would weaken source-supported identity. Neither is acceptable.

## Amendment

For **future TFG-validated revisions only**, `qa_exchange.v1.respondents[]` has two closed variants:

### Legacy respondent — unchanged

```text
{
  name,
  role,
  identity_state,
  span_indexes
}
```

Use when the respondent role is directly supported by the structured answer-turn segment role and no incompatible same-revision title evidence exists.

### Extended respondent — roster/title-supported role

```text
{
  name,
  role,
  identity_state,
  span_indexes,
  identity_evidence: {
    schema: "qa_respondent_identity_evidence.v1",
    method: "transcript_roster",
    role_source_spans: [source_span.v1, ...]
  }
}
```

Use only when `role` is supported by replayable participant/title text elsewhere in the **same exact transcript revision** rather than by the respondent's answer-turn segment role.

The parent exchange remains `qa_exchange.v1`. This amendment does not create `qa_exchange.v2`, a second Q&A store, a person registry, or a new top-level `event_workspace` key.

## Closed nested contract

`qa_respondent_identity_evidence.v1` exact keys:

```text
schema
method
role_source_spans
```

Law:

- `schema == "qa_respondent_identity_evidence.v1"`;
- `method == "transcript_roster"` in V1;
- `role_source_spans` is a non-empty ordered list of canonical `source_span.v1` objects;
- every role source span is `byte_replayed` against the same `document_id` and `document_sha256` as the parent exchange;
- the validator replays the exact source bytes and independently verifies that the declaration binds the respondent name/unique source-native alias to the published role/title;
- the source title phrase must not be truncated or replaced with a generic label merely to fit a consumer;
- `identity_state` remains exactly `source_supported`;
- no accepted extended respondent may have an empty role;
- incompatible explicit segment-role vs roster/title evidence is a refusal (`management_identity_conflict`), not a choice of preferred source;
- missing role/title support is a refusal (`management_identity_insufficient`), not an extended respondent.

## Compatibility / rollout law

This is a **contract amendment, not current production authorization**.

TFG-1 may implement and test both closed variants in Macro while the production accepted-revision gate remains AAPL-only. Existing AAPL objects and immutable generations remain legacy four-key respondents and need no migration.

No extended respondent may reach canonical production publication until the later fresh-OOS consumer vertical has:

1. updated Terminal's verified reader/type contract to accept **exactly** the legacy four-key variant or the frozen extended five-key variant;
2. added hostile exact-key tests so arbitrary sixth keys still fail;
3. proved legacy AAPL readback remains byte/semantic compatible;
4. proved the extended `role_source_spans` are same-revision and replayable before rendering the role;
5. completed the normal real-product acceptance for that fresh OOS event.

Until those consumer gates exist, production admission must remain on revisions whose accepted objects use the already-supported legacy shape.

If TFG-1 discovers that this dual-variant contract cannot be implemented without weakening existing immutable-generation reads or parent `qa_exchange.v1` semantics, it must stop and return to Sol. A builder may not silently bump `qa_exchange.v2` or make `role` optional.

## What this supersedes / preserves

Supersedes only E3-0 §7's implicit assertion that **all future source-supported respondent roles can be evidenced solely by the answer-turn segment's four-key row**.

Preserves:

- `qa_exchange.v1` parent identity and revision-scoped `exchange_id`;
- ordered one-row-per-management-answer-turn semantics;
- required non-empty source-supported respondent name + role on accepted answer turns;
- exact source replay / revision match / rights hard gates;
- no external identity/title inference;
- no model authority for Q&A structure or identity;
- `event_workspace.v1` parent schema;
- all AAPL E3-B production behavior;
- E3-P lock until a fresh untouched OOS production pass.
