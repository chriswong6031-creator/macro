# Dislocation P0-S1F — source precision and honest-N feasibility freeze

**Date:** 2026-08-23  
**Authority:** Sol P0-S1F commission; research/source-only; zero rank, gate, size,
candidate, Prophet, Radar, Fusion, execution, price, counterfactual, or outcome
authority.  
**Pickup main:** `395db13b9dadf4975e0ed43c68d02983134ddbff`  
**Prior accepted evidence:** PR #6258, merge
`3a742388e9751eb3a464cab6d80a13deb0f7a09d`, immutable K-packet
`665628e8d1d217b15239091ca6a4963a2196b3b36c4f850c18a85a0f8da8781e`.

**Later specific runtime ruling (Chairman, 2026-08-24):** independent audits and
the all-seventy relationship reconciliation run through Warp/Oz on Grok 4.6,
not Claude Web/Opus. `DEC:DISLOCATION-S1F-AUDITOR-RUNTIME-GROK46` supersedes
only the older auditor-runtime choice; every source, evidence, ontology,
cardinality, measurement, authority, and stop constraint in this freeze remains
unchanged.

## Decision

S1F is a prospective, price-blind source-precision test between the frozen
`CandidateHit` and expensive semantic review. It adds a deterministic **shadow
view**, not a source truth plane and not an event classifier. The view can describe
source context and propose `RETAIN`, `DEFER`, or `HARD_REFUSAL`; it cannot skip a
packet in S1F and cannot assert an event family or episode.

This file, `p0_s1f/S1F_TRIAGE_RULESET.json`,
`p0_s1f/S1F_MEASUREMENT_CONTRACT.json`,
`p0_s1f/S1F_AUDIT_BATCH_POLICY.json`, and
`p0_s1f/S1F_OFFICIAL_SEC_SOURCE_RECEIPT.json` are frozen and hashed before the
fresh validation selection is run or any fresh validation document byte is
materialized/read. Their post-freeze hashes are bound by a separate immutable
prospective-freeze receipt. Results cannot mutate these artifacts. A revised rule
requires a new version and a disjoint validation sample.

## Controlling source law

Precedence is:

1. Sol P0-S1F commission, 2026-08-23;
2. `DISLOCATION_P0_A1R_SOURCE_LAW_AMENDMENT_2026-08-22.md` and
   `DEC:DISLOCATION-P0-A1R-SOURCE-LAW-RECONCILIATION`;
3. merged Turn-5 source architecture, PR #6068 / merge
   `fab129e21335253c17a034ab7f6c0e57f77e5acd`;
4. Turn-4 Cross-Issuer P0 preregistration;
5. merged PR #6258 evidence, as immutable development evidence rather than a
   validation set.

No collision was found. The existing 146/146 completed query-cell estate and
277,549-candidate pool remain frozen. S1F does not rerun FTS, change phrases,
change the seed or selection key, select with semantics, or top up.

Every CIK in `p0_a1r/A1R_EXACT20_SOURCE_SELECTION.json` is
`SOURCE_DESIGN_EXCLUDED` from S1F and later confirmatory P0 origin N. This is an
issuer-wide exclusion even though packet uniqueness remains exactly
`(CIK, accession)`. Endeavour Silver / EXK / CIK `0001015647` remains excluded by
the preregistration and prior source law.

## Frozen fresh-seventy selection

Eligible strata, in governing order, are:

1. `PHYSICAL_MECHANICAL_INTERRUPTION`
2. `EXTERNAL_HUMAN_INTERRUPTION`
3. `CYBER_OR_IT_INTERRUPTION`
4. `WEATHER_OR_PHYSICAL_DISASTER`
5. `TEMPORARY_EXPECTATION_RESET`
6. `STRUCTURAL_IMPAIRMENT_CONTROL`
7. `RESOLVED_BEFORE_DISCLOSURE_CONTROL`

Select exactly ten packets per stratum. Each ten contains exactly seven modern and
three development packets and exactly seven 8-K and three 6-K packets. Packets are
globally unique by `(CIK, accession)`; the same CIK may recur at a different
accession unless it is a source-design-excluded CIK. Every query edge on a selected
identity survives. Selection is the lexicographically smallest feasible exact set
in ascending frozen `selection_key` order. The feasibility decision consumes only
frozen candidate metadata, never document bytes, triage, model semantics, price, or
outcomes. Infeasibility is a named blocker; no margin, phrase, or row is changed.

`MACRO_OR_INDUSTRY_WIDE` stays out as `SOURCE_CAPACITY_SHORTFALL`; S1F invents no
macro phrase.

## Canonical source materialization

Each selected packet consumes the generic SEC source/document owners proven by
#6258:

```text
frozen CandidateHit and all query edges
    -> canonical broad-SEC filing receipt
    -> canonical sec_document_spine filing/document manifest
    -> every exact (accession, FTS-matched filename) archive member
    -> additive primary 8-K/6-K report context through the same owner
    -> source-only evidence catalog
```

The exact FTS-matched archive member is mandatory. The filing cover/primary
document is additive context and cannot substitute for a matched exhibit. Missing,
ambiguous, cross-accession, hash-divergent, or unreplayable material fails closed.
No local receipt plane, fallback, filing truth store, or duplicate issuer identity
is permitted. `accepted_at` is the primary SEC decision clock; `filed_on` stays a
date label; retrieval/recorded clocks are provenance only.

The source and audit workspaces must physically omit directories or fields for
price, market, outcome, counterfactual, ranking, sizing, execution, Prophet, Radar,
or Fusion. Network access is restricted to official SEC hosts during source
materialization. Model and audit workspaces have network access `NONE` except the
declared model transport itself and contain only the self-contained source packet
bundles.

## Shadow triage boundary

Allowed inputs are frozen query provenance, canonical filing/document identity,
exact `accepted_at`/`filed_on`, canonical document role/type/description when the
owner actually supplies it, 8-K item codes, exact FTS-matched bytes, and additive
primary/current-report bytes. Filename patterns are supporting provenance only and
never authoritative document classification.

Allowed outputs are:

- one or more source-context categories;
- shadow disposition `RETAIN`, `DEFER`, or `HARD_REFUSAL`;
- exact deterministic rule IDs;
- exact metadata evidence and byte-offset evidence spans;
- typed gaps and all-false authority flags.

Forbidden outputs include P0/event family, episode identity or relationship,
probability, score, rank, market expectation, price/outcome field, trading
conclusion, authority, or semantic admission. Retrieval family remains provenance
only.

All phrase matching is performed against raw document bytes with ASCII
case-folding, and all evidence offsets are raw byte offsets. Every query phrase
occurrence in every exact matched document must be located before a hard refusal is
possible. Decoding failure, an unlocated occurrence, missing source context, or
mixed/ambiguous context yields `DEFER`, never a hard refusal.

### Rule precedence

1. **Fail-closed source gap.** A missing/unreplayable exact matched document,
   missing exact acceptance clock, unresolved owner identity, or incomplete phrase
   accounting yields `DEFER` plus the typed gap. The packet remains a source failure
   and cannot masquerade as a completed audit input.
2. **High-information 8-K current-event anchor.** Canonical item codes `2.04`,
   `2.05`, `2.06`, and `4.02` propose `RETAIN`. Item `1.05` proposes `RETAIN` only
   for an accepted timestamp on or after `2023-12-18T00:00:00Z`; earlier use has no
   strong-anchor effect. A strong item code never supplies P0 family/admission.
3. **Realized current-report context.** Exact primary/current-report or
   event/press-release context that uses a frozen realized-context signature around
   the phrase proposes `RETAIN`. Hypothetical, definition, covenant, or negated
   occurrences do not satisfy this rule. This is only a source-context statement.
4. **Item 2.02 and completed-period results.** Item `2.02` is not globally
   excluded. A realized current-event context can retain it. Ordinary completed-year
   or completed-quarter results alone yield `DEFER`; the triage does not decide
   whether the semantic model can support a temporary expectation reset.
5. **Form 6-K.** It has no closed 8-K item taxonomy. A 6-K retains only on exact
   realized issuer-specific current-report/event-release context; otherwise it
   defers or reaches a fully proven structural hard-refusal rule.
6. **Hard-refusal candidates.** `CERTIFICATION_ONLY`,
   `AGREEMENT_COVENANT_DEFINITION_ONLY`, and `HYPOTHETICAL_RISK_ONLY` may propose
   `HARD_REFUSAL` only when every phrase occurrence is byte-accounted within that
   one class across all exact matched documents, no realized context is present,
   and no stronger item/current-report anchor applies.
7. **No aggressive refusal for noisy commercial context.** Ordinary financing,
   capital-return, offering, repurchase, transaction, and completed-period results
   contexts propose `DEFER`, not `HARD_REFUSAL`, in v1.
8. **Default.** Anything else is `UNRESOLVED_SOURCE_CONTEXT` / `DEFER`.

The exact signatures, window size, precedence, and output schema live in the frozen
JSON rule set. Code is an executable interpretation of that file and tests must fail
if the implementation and frozen constants drift.

## Prospective audit protocol

Triage has zero skip authority. All seventy packets proceed to a fresh source-only
Grok proposal and an independent source-only Grok 4.6 audit under the accepted #6258
semantic/episode ontology. Neither model receives price/outcome data. The independent
auditor is not shown the prior #6258 semantic outputs as truth and is not shown the
new shadow disposition before it renders its semantic verdict.

The predetermined transport policy is seven ten-packet batches, one per retrieval
stratum in governing order, with packets ordered by frozen selection key. Batch
bindings are derived once from the selected seventy and never rearranged for
attachment convenience or expected yield. A final all-seventy reconciliation pass
reviews amendments, duplicate disclosure pulses, mitigation/resolution transitions,
and economic-episode origin identity across batch boundaries. Accession count is not
episode N.

Every non-null semantic assertion cites exact source bytes. Typed `UNKNOWN`,
`UNAVAILABLE`, `RIGHTS_BLOCKED`, `NOT_APPLICABLE`, `EXPLICIT_NONE`, `CORRECTED`,
and `QUARANTINED` remain distinct. Only a final independent `ACCEPT` or `REPAIR`
that satisfies the accepted P0 adverse/control ontology can admit a transition or
episode. `REJECT` and typed null/refusal packets admit none.

## Frozen measurement law

The unit is a distinct independently audited economic-episode origin after final
all-seventy linkage, not a candidate, accession, filing, query edge, transition, or
model proposal. Each episode contributes once to overall N through its designated
origin packet. Measurement code joins the already-frozen triage view only after the
independent audit/linkage truth is complete.

Report raw origin count and a two-sided 95% Clopper-Pearson exact binomial interval
for:

- all seventy;
- each seven source strata (denominator ten);
- modern (49) and development (21);
- 8-K (49) and 6-K (21);
- each observed matched-document-role class.

Role class is derived only from canonical owner roles across exact FTS-matched
documents: `PRIMARY_ONLY`, `ARCHIVE_ONLY`, `MIXED`, or `UNRESOLVED`. Additive
primary context does not relabel an archive-only match.

Also report:

- modern-origin yield;
- shadow retain rate `R / 70`;
- admitted-origin precision inside retain `K_R / R`;
- identities of admitted origins proposed suppressed by `DEFER` and by
  `HARD_REFUSAL`, separately;
- enrichment `(K_R / R) / (K / 70)`, with a typed undefined result for zero
  denominator;
- candidates reviewed per admitted origin `70 / K`;
- unique model-reviewed source bytes per admitted origin, deduplicating by canonical
  document SHA-256 across exact matched plus additive context bytes;
- dominant independently audited false-positive mechanisms as counts, without
  converting retrieval families into semantic labels.

Every proportion uses the declared fixed denominator and exact interval. Zero
denominators and zero origins are printed as typed results, never NaN, infinity,
zero-filled success, or omitted rows.

If any admitted origin is in a proposed `HARD_REFUSAL`, that rule is
`UNSAFE_FOR_PROMOTION` and cannot be patched against the same seventy. A 0/10
primary-family result is `SOURCE_FEASIBILITY_UNPROVEN`, not impossibility. Zero
modern origins across all 49 modern packets yields `SOURCE_PRECISION_NOT_PROVEN`.

## Mining/core partition ruling

The current Stage industry adapter publishes percentile facts and resolves current
security/industry IDs; it does not provide a canonical CIK-to-metals/mining
classification. No other current canonical issuer/sector owner inspected at pickup
provides the required point-in-time CIK partition. S1F therefore records
`SECTOR_PARTITION_UNRESOLVED` and does not infer sector from ticker, issuer name,
query family, SIC guessing, or a new Dislocation taxonomy.

Overall S1F validation proceeds, but P0-S2 stays blocked until a canonical owner can
resolve the non-mining core versus external-validation mining partition.

## Failure and stop law

Stop with a named blocker on selection infeasibility, source-owner/document replay
failure, price-firewall failure, missing exact acceptance clock, incomplete model
evidence, unresolved audit disagreement, unresolved cross-packet relationship, or
candidate-order instability.

The terminal artifact is a single new draft `HOLD-FOR-SOL` PR. It remains draft,
has no `merge-on-green`, has native auto-merge null, and is not merged or marked
ready. Stop before P0-S2 and before any price, outcome, counterfactual, ranking,
sizing, execution, Prophet, Radar, or Fusion path.

## Observed source-only result — 2026-08-24

The frozen seventy completed without a top-up. Canonical owner replay remains
`COMPLETE_BYTE_IDENTICAL`: 70 packets, 129 exact FTS-matched documents, 183 unique
documents after additive primary context, and source network access `NONE` during
replay. The exact source-manifest logical SHA remains
`98740d5aeee8e0e3ae3bb8408498b72db839cdc3686b8b3994b416c99cd7a3e4`.

Seven isolated Warp/Oz conversations on runtime `grok-4-6-high` independently
audited all seventy proposals. Their merged verdict is 52 `ACCEPT`, 18 `REPAIR`,
0 `REJECT`, with 46 resolved field disagreements and 0 unresolved disagreements.
The separate all-seventy Warp/Grok 4.6 reconciliation reviewed all 70 packet IDs,
emitted 70 terminal relationship assessments, and admitted no duplicate,
amendment, pulse, mitigation, resolution, or episode edge.

The honest economic-episode-origin count is therefore **0 / 70**, not one per
accession and not the shadow-retain count. Its exact two-sided 95% Clopper-Pearson
interval is `[0.000000000000, 0.051333797151]`. Retain was 18 / 70, but retained
precision was 0 / 18; every primary family was 0 / 10. The terminal source finding
is `SOURCE_PRECISION_NOT_PROVEN`, while the separately frozen sector finding remains
`SECTOR_PARTITION_UNRESOLVED`. Neither finding is permission to alter phrases,
ontology, allocation, or admission law.

The immutable returned evidence is:

- proposal bundle SHA `02d55bcba5f1d259bb543c58e888137872cde7274dfff22a7fb599305c302532`;
- independent audit bundle SHA `f6d9cc77cadca7d7086564acd710aa8a82c0b0b9a5e199cd11f16c1ec016eaad`;
- all-seventy reconciliation SHA `2b5c6e3d624fd6d7514fed1e6bb54178f3ad12adc64b54efc46780f286713711`;
- Warp/Grok runtime-access receipt SHA `7c3ef8dbec7940a02b24545c297c8f6fc785a51a0daa4b220392f1e631156143`;
- measurement SHA `31446575f23123a3a9b2e83f7cc2057bdb0ab2a0976f460cba16262aedab3c4c`;
- K-packet SHA `572fab916e3505a05896a76784c3084af71619c88a7e39a6b4fdff1b96577b99`;
- final receipt bundle SHA `a87fb536d7c7c3c42798eacedddf18b69501573045ca6c20ac197f58ff4cdb25`.

The K-packet binds the runtime-access receipt, all authority flags are false, the
source-only structural scan passes, no forbidden data directory is present, and the
stop remains exactly before P0-S2. Sol alone decides whether the zero-yield source
experiment ends the lane or commissions a new price-blind source-law wave.
