---
key: BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK
question: >
  May the authorized 2026-08-17 BioPharmCatalyst spreadsheet snapshots reuse
  source_id biopharmcatalyst_benchmark, or do they need a distinct source identity?
answer: >
  Distinct identity. Keep biopharmcatalyst_benchmark verbatim (benchmark_only,
  proprietary_historical_row_import still prohibited). Add biopharmcatalyst_jv_snapshot
  with license_class finite_jv_snapshot_seed, production_ingest_allowed false, for
  finite authorized-seed matching, schema/clock census, and coverage scoring only.
rationale: >
  The benchmark identity is historical clean-room policy locked by
  tests/test_biocatalyst_source_registry.py::test_benchmark_products_cannot_become_data_or_code_dependencies.
  Silently widening it to admit JV row matching would rewrite a rights gate that
  forbids proprietary_historical_row_import. The JV dump is a finite operator-held
  seed, not a continuous API and not a production feed. A second id keeps those
  two meanings from collapsing.
alternatives:
  - option: Reuse biopharmcatalyst_benchmark and add permitted_uses for seed matching
    why_not: >
      Collapses clean-room benchmark policy with proprietary-row possession. The
      existing prohibited_uses list would have to be rewritten, which is the silent
      rewrite this freeze forbids.
  - option: No registry row; document seeds only in research/
    why_not: >
      Future sessions will look up source_id in config/biocatalyst_sources.yml.
      An undocumented seed identity is how a later PR imports rows under the
      benchmark id.
  - option: Commit the snapshot rows into data/ as a fixture
    why_not: >
      That is proprietary_historical_row_import. Hashes and schema belong in the
      freeze; bytes stay operator-held.
evidence:
  - "config/biocatalyst_sources.yml biopharmcatalyst_benchmark license_class benchmark_only, prohibited_uses includes proprietary_historical_row_import"
  - "tests/test_biocatalyst_source_registry.py::test_benchmark_products_cannot_become_data_or_code_dependencies"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md §2"
affects:
  - "WS:BPC-JV-RECON"
  - "biocatalyst"
  - "config/biocatalyst_sources.yml"
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-18
---

## Grounds

Partnership design makes BPC's continuous API unavailable. The authorized dump is
the only BPC evidence boundary. The benchmark source id already encodes "do not
import their rows." Matching against a finite seed is a different act and needs a
different name so tests can pin both.

## What would reopen this

An explicit Sol or Chairman instruction to fold the JV seed into the benchmark
identity, or a rights review that authorizes production ingest of BPC rows
(not requested, not recommended).
