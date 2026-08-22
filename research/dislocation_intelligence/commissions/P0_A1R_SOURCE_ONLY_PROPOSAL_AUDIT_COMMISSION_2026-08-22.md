# P0-A1R source-only proposal and audit commission

**Authority:** `DEC:DISLOCATION-P0-A1R-SOURCE-LAW-RECONCILIATION` and
`DISLOCATION_P0_A1R_SOURCE_LAW_AMENDMENT_2026-08-22.md`.  
**Scope:** exactly twenty canonical-owner SEC packets; source-only; no network,
prices, outcomes, counterfactuals, scoring, ranking, or execution authority.

## Inputs and proposal pass

The coordinator supplies exactly twenty packets with a unique `(cik, accession)`,
canonical document id, canonical document SHA-256, and the byte payload used for
review. Grok receives only those packets and returns a proposal for each packet.
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
Economic episode count derives only from audited accepted/repaired `episode` edges,
never from the number of accessions.

Run `scripts/research/dislocation_p0_a1r_semantic_contract.py` in-memory over the
twenty source-byte packets and proposals. It returns only summaries/refusals/unknowns/
disagreements/episodes and writes no files or external state. Any failure is a typed
refusal, not an invitation to use local #6117 receipt or episode truth.

## Stop

Return a draft HOLD-FOR-SOL packet after all twenty pass this contract. Stop before
P0-S2 and before any price, counterfactual, outcome, or market-data access.
