# Grok Worker Handoff — P0-S1 Blind Source Extraction Pilot

## Observable mission

Given exactly 20 deterministic P0 source packets produced by P0-S0, propose evidence-backed event transitions and economic-episode links without accessing any price, volume, chart, return, casebook or outcome data.

Done means every source packet has either:

- a complete proposed transition with exact evidence spans; or
- a typed refusal explaining why the source cannot support classification.

## Why it matters

Turn 5 proved candidate capacity but also proved that search hits, item codes and filing dates are not event intelligence. This pilot tests whether Mastermind can convert exact official documents into useful, auditable impairment context before scaling to hundreds of events.

## Authority and precedence

1. Chairman’s Dislocation Intelligence outcome.
2. `DISLOCATION_CROSS_ISSUER_P0_PREREG_2026-08-20.md`.
3. `DISLOCATION_TURN5_SOURCE_ARCHITECTURE_FREEZE_2026-08-20.md`.
4. Canonical SEC filing/document receipts.
5. This handoff.
6. Model convenience last.

No output has market or trading authority.

## Verified current state and recent PRs

- PR #6057: canonical EXK execution; closed unmerged.
- PR #6060: Turn 4 architecture/P0 records.
- PR #6061: price-blind local-source census; passed and closed unmerged.
- PR #6062: price-blind SEC FTS capacity census; passed and closed unmerged.
- Turn 4 EXK replay has zero untouched confirmation-arm entries.
- Every P0 temporary family has modern 8-K and 6-K candidate capacity.
- FTS form filters admit `/A` amendments and broad cells can reach 10,000 results.
- Native SEDAR+ public automation is rights-blocked; P0.1 uses SEC-reporting issuers.
- Exact filing/document receipt primitives exist in the canonical SEC document spine.

## Exact scope and repositories

Repository: `macro`.

Input:

- 20 JSON source packets conforming to `mastermind.dislocation_p0.source_candidate.v1`;
- exact source documents or bounded document views identified by content hash;
- no market-data mount.

Output per packet:

- proposed event family or refusal;
- affected scope;
- adverse-information state at t0;
- uncertainty/duration state;
- recoverability evidence type;
- structural-impairment evidence;
- asset integrity;
- quantified impact only when explicit;
- mitigation/resolution state;
- event occurrence date only when explicitly sourced;
- exact evidence spans for every populated field;
- proposed duplicate/amendment/pulse/episode relationships;
- uncertainty notes.

## Explicit non-goals

Do not:

- decide whether the stock was cheap;
- predict recovery or returns;
- infer management or institutional intent;
- inspect charts or market reactions;
- turn sentiment into severity;
- assign probabilities or scores;
- choose or reorder candidates;
- skip difficult rows silently;
- write final audited truth;
- alter the source packet or query receipt.

## Complete machine journey

```text
source packet
→ verify document hash
→ identify adverse proposition
→ extract exact supporting spans
→ populate independent economic axes
→ test structural-control alternatives
→ propose transition/episode links
→ emit PROPOSED or typed REFUSAL
→ hand to Fable/Opus auditor
```

## Data, contract, time, null and correction behavior

- Use `accepted_at` as the SEC-source decision clock.
- `filed_on` is date-only and never an intraday clock.
- Do not infer `event_occurred_at`.
- Later mitigation/resolution is a separate transition.
- `/A` is an amendment/correction, not an origin unless the amendment itself introduces new adverse information and the auditor explicitly rules it so.
- `UNKNOWN`, `UNAVAILABLE`, `RIGHTS_BLOCKED`, `NOT_APPLICABLE`, `EXPLICIT_NONE`, and `CORRECTED` remain distinct.
- Source silence is `UNKNOWN`, not “no impairment.”
- `intent_orchestration` stays `UNKNOWN`.

## Deterministic vs statistical vs model-generated method

Deterministic inputs:

- candidate order;
- IDs and clocks;
- source-document identity/hashes;
- text offsets;
- query provenance.

Model-generated proposals:

- semantic event fields and episode relationships.

No statistical or market model is in scope. The model may not calculate probabilities, market features or expected returns.

## Failure states

Return a typed refusal for:

- no adverse event in source;
- query phrase appears only in boilerplate or historical discussion;
- exact event scope cannot be determined;
- recoverability is unsupported;
- event is structural or mixed beyond the schema;
- document hash/view mismatch;
- amendment/duplicate relationship unresolved;
- identity conflict;
- source document unavailable;
- evidence spans contradict proposed fields.

## Ordered implementation sequence

1. Validate packet schema and hashes.
2. Read only the supplied source documents.
3. Extract literal facts before assigning any family.
4. Test at least one structural-impairment alternative.
5. Populate fields only from accepted spans.
6. Link duplicate/pulse/mitigation/resolution transitions.
7. Run internal contradiction check.
8. Emit canonical proposal JSON.
9. Produce a continuation note for the auditor.

## Acceptance tests and real proof

- 20/20 packets return proposal or typed refusal.
- Every populated economic field has an exact evidence span.
- Zero price/outcome vocabulary appears outside explicit non-goal metadata.
- Zero probabilities, rankings or trade language.
- All amendments and duplicates are explicit.
- Two identical source packets produce byte-identical proposals under fixed model settings, or nondeterminism is disclosed.
- At least five intentionally ambiguous/control cases remain `UNKNOWN` or refused where evidence is insufficient.
- Fable/Opus can replay every span against the document hash.

## Stop condition

Stop after 20 proposed source annotations and the refusal ledger. Do not expand candidate count, see prices, audit yourself or recommend P0 promotion.

## Required continuation handoff

Return:

- packet IDs and input manifest SHA;
- proposal bundle SHA;
- proposal/refusal counts by family;
- all disagreements and ambiguities;
- every source/document failure;
- exact auditor command/input;
- confirmation that no market paths were mounted.