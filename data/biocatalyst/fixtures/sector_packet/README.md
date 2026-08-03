# BC-N0a sector-packet inputs

`operational_health.v1.passed.json` is a bounded public operational-health DTO
paired with the committed ClinicalTrials.gov `trial_snapshot.v1` fixture.
The compiled snapshot alone does not contain a public-generation manifest or
pointer receipt, so generation-commit provenance remains the upstream public
publication boundary's responsibility; N0a validates the immutable projection
contract and never follows a raw-store path to reconstruct it.

`trial_snapshot.v1.evidence_claim_refs` is not an independently attested claim
allowlist. N0a may bind the projection and its source record, but its public
`evidence_claim_refs` and `current_fact_refs` remain empty until a successor
contract supplies that independent provenance. Same-NCT syntax is not proof.

Freshness is derived only from the ClinicalTrials.gov v2 `/version`
`dataTimestamp` that the upstream committed receipt observed. The active launch
SLO fixes its budget at 7,200 seconds. A lexical ClinicalTrials timestamp
without `Z` or an explicit numeric offset is retained as a source fact but
emits `unknown` freshness; it is never assumed to be UTC.

The internal boundary is intentionally finite: at most 100 trial projections,
256 KiB canonical/preflight bound per projection, 1 MiB aggregate projection
input, 32 evidence refs per projection (1,000 aggregate), and a 1 MiB final
packet. Health is capped at 16 KiB; each injected governance document at
256 KiB; all JSON inputs are additionally bounded by 20,000 nodes, depth 32,
and 4,096 items per container before canonical serialization. Final carrier
bytes also receive a quote-aware lexical nesting scan before JSON decoding.
Preparation retains each normalized projection as separate canonical bytes,
plus bounded canonical health, lobe-run, and authority-manifest bytes. Final
materialization decodes those immutable copies under the same limits, reruns
the complete binding validation, reconstructs the packet, and requires exact
canonical byte equality before returning it.

There is intentionally no committed lobe-run or authority-manifest fixture for
the final compiler path.  Those references are governance-owned runtime inputs,
not BioCatalyst fixture authority.  Tests create explicit injected objects from
the non-authorizing `plan_sector_packet_binding` receipt, then prove the final
compiler rejects placeholders, missing bindings, expiry, kill switches, and
unplanned references.
