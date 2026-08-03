# BC-N0a sector-packet inputs

`operational_health.v1.passed.json` is a bounded public operational-health DTO
paired with the committed ClinicalTrials.gov `trial_snapshot.v1` fixture.
The compiled snapshot alone does not contain a public-generation manifest or
pointer receipt, so generation-commit provenance remains the upstream public
publication boundary's responsibility; N0a validates the immutable projection
contract and never follows a raw-store path to reconstruct it.

There is intentionally no committed lobe-run or authority-manifest fixture for
the final compiler path.  Those references are governance-owned runtime inputs,
not BioCatalyst fixture authority.  Tests create explicit injected objects from
the non-authorizing `plan_sector_packet_binding` receipt, then prove the final
compiler rejects placeholders, missing bindings, expiry, kill switches, and
unplanned references.
