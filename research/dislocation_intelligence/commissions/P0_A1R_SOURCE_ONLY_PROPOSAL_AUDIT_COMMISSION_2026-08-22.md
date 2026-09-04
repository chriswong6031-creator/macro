# P0-A1R source-only proposal and audit commission

**Authority:** `DEC:DISLOCATION-P0-A1R-SOURCE-LAW-RECONCILIATION` and
`DISLOCATION_P0_A1R_SOURCE_LAW_AMENDMENT_2026-08-22.md`.
**Scope:** exactly twenty canonical-owner SEC packets; source-only; no network,
prices, outcomes, counterfactuals, scoring, ranking, or execution authority.

## Inputs and proposal pass

The coordinator supplies exactly twenty packets with a unique `(cik, accession)` and
every canonical SEC document matched by that filing's frozen FTS query edges. Each
document carries its canonical id, exact archive filename, SHA-256, and byte payload
used for review. The primary/cover filing document may not replace an FTS-matched
exhibit. Grok receives only those packets and returns a proposal for each packet.
It may populate only these semantic fields:

`event_family`, `affected_scope`, `adverse_information_state`,
`duration_uncertainty`, `recoverability_evidence`,
`structural_impairment_evidence`, `quantified_impact`,
`mitigation_resolution_transition`, and `episode_relationship`.

Every asserted value carries an exact excerpt, byte start/end offsets, and the matching
packet document SHA-256. Typed states `UNKNOWN`, `UNAVAILABLE`, `RIGHTS_BLOCKED`,
`NOT_APPLICABLE`, `EXPLICIT_NONE`, `CORRECTED`, and `QUARANTINED` are mappings with
a distinct `state`, never nulls. `UNKNOWN`, `UNAVAILABLE`, `RIGHTS_BLOCKED`, and
`NOT_APPLICABLE` may omit source evidence only because they assert no source fact;
when evidence is supplied it must replay exactly. `EXPLICIT_NONE`, `CORRECTED`, and
`QUARANTINED` are affirmative source assertions and always require replayable source
evidence. Query-family is retrieval provenance, never a semantic assertion.

## Independent audit and completion

Fable/Opus independently records `ACCEPT`, `REPAIR`, or `REJECT` for every proposal;
no same-function second pass is an audit. An `ACCEPT` binds the proposed values as
final. A `REPAIR` supplies complete final repaired semantic values that independently
pass the same evidence-replay rules. A `REJECT` supplies a typed refusal. Every
disagreement must have an explicit terminal resolution before the packet set can pass.

Duplicate, amendment, pulse, mitigation, resolution, and episode relationships are
explicit edges naming all linked packet IDs. Every edge carries replayable source
evidence plus independent Fable/Opus audit role/verdict and terminal resolution.

An audited relationship is necessary but not sufficient for P0 episode admission.
At least one linked packet must have a final audited semantic assertion, backed by an
exact source span, with one of these controlled values in its corresponding field:

- `adverse_information_state = P0_ADVERSE_INFORMATION`;
- `structural_impairment_evidence = P0_STRUCTURAL_IMPAIRMENT_CONTROL`;
- `mitigation_resolution_transition = P0_RESOLVED_BEFORE_DISCLOSURE_CONTROL`.

For `ACCEPT`, final means the Grok proposal. For `REPAIR`, final means Opus's complete
`final_semantic`. `REJECT` has no final semantic and cannot enter an episode. Typed
states—including `UNKNOWN`, `UNAVAILABLE`, and `NOT_APPLICABLE`—never satisfy this
admission rule. An ordinary dividend, offering, buyback, agreement, joint venture, or
earnings announcement therefore cannot become a P0 episode merely because it is an
economic event or because an episode relationship was proposed. Economic episode
count derives only from resolved, independently audited `episode` edges whose linked
final semantics pass this P0-eligibility rule, never from accession count.

Run `scripts/research/dislocation_p0_a1r_semantic_contract.py` in-memory over the
twenty source-byte packets and proposals. It returns only summaries/refusals/unknowns/
disagreements/episodes and writes no files or external state. Any failure is a typed
refusal, not an invitation to use local #6117 receipt or episode truth.

## Stop

Return a draft HOLD-FOR-SOL packet after all twenty pass this contract. Stop before
P0-S2 and before any price, counterfactual, outcome, or market-data access.
