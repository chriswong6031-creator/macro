---
key: GOVREV-SBIR-RAIL-IS-A-SHIPPED-COLLECTOR-ONLY-WAVE
claim: >
  The Government Revenue SBIR/STTR rail is fully built and fully registered — collector,
  engine module, synapse entry, DAG entry, collect.py adapter, append-only fence and CI
  suite — yet has committed zero data artifacts in the 19 days since it landed, has zero
  product consumers, and has zero contract schema files despite declaring five contract
  names in code.
falsifier: >
  `git ls-files data/government_revenue/ | grep sbir` returning any path, or
  `grep -rn sbir_progression scripts/build_government_revenue*.py app/government_revenue.py`
  returning a non-test importer, or `git ls-files contracts/ | grep sbir` returning a schema
  file. Any one of the three disproves the corresponding half of the claim.
so_what: >
  A future session must not read SBIR's presence in config/synapse.yml, config/dag.yml, and
  .github/ci/legacy-jobs.yml as evidence the rail works — that registration is exactly what
  makes it look complete in a census. Registration and a green unit suite are not production.
  Before proposing any new D6 rail, check whether an existing rail is dark first; and treat
  "collector exists" as DARK_OR_DISCONNECTED until a committed artifact with a real clock and
  a named consumer are both found.
kind: dead_code
verified_at: 2026-08-27
verified_by: >
  `git ls-files --error-unmatch data/government_revenue/sbir_*` (all five ABSENT, against a
  positive control of 35 present fms_*/dod_budget_* artifacts); collectors/sbir_awards.py:70-74
  (five contract names) vs empty `git ls-files contracts/ | grep -i sbir`;
  config/synapse.yml:17269; config/dag.yml:3991; scripts/collect.py:199,398;
  config/append_only_artifacts.json:39; .github/ci/legacy-jobs.yml:9184-9191;
  landed ec28d15709fe (PR #5012, 2026-08-09).
scope:
  - macro
  - government-revenue-foresight
  - collectors/sbir_awards.py
  - engine/government_revenue/sbir_progression.py
confidence: verified
---

The rail landed as PR #5012 ("govrev: Wave 10 rail 3 — SBIR progression evidence lane") on
2026-08-09 and is registered everywhere a healthy rail would be:

- `config/synapse.yml:17269` declares `data/government_revenue/sbir_award_observations.parquet`
  with `storage: git` and `freshness_sla_hours: 168`;
- `config/dag.yml:3991` declares five reads and five writes;
- `scripts/collect.py:199` registers the adapter and `:398` puts it in the nightly-only set;
- `config/append_only_artifacts.json:39` fences the receipts as append-only;
- `.github/ci/legacy-jobs.yml:9189` runs `pytest tests/test_sbir_awards.py`, twice.

None of the five declared artifacts exists in git. No builder, app module, or site asset
imports `sbir_progression`; the only importers are under `tests/`. No
`site/government-revenue-data/sbir-*.json` exists. The five contract names at
`collectors/sbir_awards.py:70-74` have no corresponding files in `contracts/government_revenue/`,
which does carry `government_fms_case.v1.schema.json` for the accepted FMS rail.

The CI presence is itself a tell: `legacy-jobs.yml:9184` records that the lane "landed named by
no `run:` step — the unrun-suite gate reds main on it", so the suite was backfilled to satisfy a
gate rather than to prove production. A unit suite over a collector that has never persisted a
row is the "cosmetic green that hides stale/partial coverage" failure class.

Why it is dark is **not** established by this discovery. A single read-only probe of
`api.www.sbir.gov/public/api/awards` from a developer host returned HTTP 403, but that probe
failed its own positive control (`dsca.mil` and `sec.gov`, both provably collected in
production, also return 403 to a bare request) — see
[[DSC-OFFICIAL-SOURCE-403-TO-A-BARE-PROBE-CARRIES-NO-SIGNAL]]. The collector is written so that
"a source failure leaves the accrued ledger, activation state, and status exactly as they were",
which makes a persistently-refusing source and a never-activated collector observationally
identical from the repository. Distinguishing them requires reproducing the request from the
runner.

Related: [[DSC-GOVREV-PAGE-FENCE-PEAK-IS-THE-SAM-EVIDENCE-BAKE]].
