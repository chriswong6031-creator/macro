---
key: BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK
question: >
  May the authorized 2026-08-17 BioPharmCatalyst spreadsheet snapshots reuse
  source_id biopharmcatalyst_benchmark, or do they need a distinct source identity?
answer: >
  PROPOSED pending Sol. Distinct identity. Keep biopharmcatalyst_benchmark
  verbatim (benchmark_only, proprietary_historical_row_import still prohibited
  there). Add biopharmcatalyst_jv_snapshot with license_class
  licensed_finite_snapshot. production_ingest_allowed stays false because it is
  the continuous-producer gate, not a ban on licensed snapshot use. Finite-snapshot
  capabilities (import/storage, repo normalization, product projection, research)
  are allowed under DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN. This is not a
  matching-only / never-git identity.
rationale: >
  The benchmark identity is historical clean-room policy locked by
  tests/test_biocatalyst_source_registry.py::test_benchmark_products_cannot_become_data_or_code_dependencies.
  Silently widening it to admit JV snapshot use would rewrite a rights gate that
  forbids proprietary_historical_row_import. A second id keeps clean-room
  benchmark policy from collapsing into licensed finite-snapshot rights.
  Fable is not the final architecture decision-maker; Sol reviews this freeze.
alternatives:
  - option: Reuse biopharmcatalyst_benchmark and add permitted_uses for snapshot import
    why_not: >
      Collapses clean-room benchmark policy with licensed snapshot possession.
      The existing prohibited_uses list would have to be rewritten, which is the
      silent rewrite this freeze forbids.
  - option: No registry row; document snapshots only in research/
    why_not: >
      Future sessions will look up source_id in config/biocatalyst_sources.yml.
      An undocumented snapshot identity is how a later PR imports rows under the
      benchmark id.
  - option: Matching-only operator-held never-git identity
    why_not: >
      Withdrawn. Chairman confirmed storage, product, repo, and research use
      (DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN). This PR still does not ingest
      rows; that is freeze scope, not a rights ban.
evidence:
  - "config/biocatalyst_sources.yml biopharmcatalyst_benchmark license_class benchmark_only, prohibited_uses includes proprietary_historical_row_import"
  - "config/biocatalyst_sources.yml biopharmcatalyst_jv_snapshot license_class licensed_finite_snapshot, production_ingest_allowed false"
  - "tests/test_biocatalyst_source_registry.py::test_biopharmcatalyst_jv_snapshot_is_distinct_from_the_benchmark"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md §2"
  - "PR #5909 Sol REQUEST CHANGES 2026-08-19"
affects:
  - "WS:BPC-JV-RECON"
  - "biocatalyst"
  - "config/biocatalyst_sources.yml"
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-18
review_by: 2026-08-22
---

## Grounds

Partnership design makes BPC's continuous API unavailable. The authorized dump
is the only BPC evidence boundary. The benchmark source id already encodes
"do not import their rows" for the clean-room product. Licensed finite-snapshot
use is a different act and needs a different name so tests can pin both.
This record is a proposed ruling pending Sol, not Fable-final architecture.

## What would reopen this

Sol rejecting the distinct-id split, or an explicit Chairman instruction to
fold the JV snapshot into the benchmark identity.
