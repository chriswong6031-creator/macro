---
key: BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK
question: >
  May the authorized 2026-08-17 BioPharmCatalyst spreadsheet snapshots reuse
  source_id biopharmcatalyst_benchmark, or do they need a distinct source identity?
answer: >
  Accepted. Distinct identity. Keep biopharmcatalyst_benchmark
  verbatim (benchmark_only, proprietary_historical_row_import still prohibited
  there). Canonical source identity biopharmcatalyst_jv_snapshot with
  license_class licensed_finite_snapshot is frozen now. production_ingest_allowed
  stays false because it is the continuous-producer gate, not a ban on licensed
  snapshot use. Finite-snapshot capabilities (import/storage, repo
  normalization, product projection, research) are allowed under
  DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN. This is not a matching-only /
  never-git identity. Runtime registry insertion and machine-enforced
  source-registry tests are deferred to the post-soak successor source-registry
  / successor launch-manifest transition
  (DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK).
rationale: >
  The benchmark identity is historical clean-room policy locked by
  tests/test_biocatalyst_source_registry.py::test_benchmark_products_cannot_become_data_or_code_dependencies.
  Silently widening it to admit JV snapshot use would rewrite a rights gate that
  forbids proprietary_historical_row_import. A second id keeps clean-room
  benchmark policy from collapsing into licensed finite-snapshot rights.
  Sol accepted this ruling on 2026-08-19 (PR #5909).
alternatives:
  - option: Reuse biopharmcatalyst_benchmark and add permitted_uses for snapshot import
    why_not: >
      Collapses clean-room benchmark policy with licensed snapshot possession.
      The existing prohibited_uses list would have to be rewritten, which is the
      silent rewrite this freeze forbids.
  - option: No registry row; document snapshots only in research/
    why_not: >
      Omitting the canonical identity entirely is how a later PR imports rows
      under the benchmark id. Freeze and DECs name biopharmcatalyst_jv_snapshot
      now; the live YAML row waits for the post-soak successor registry
      (DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK), it is not cancelled.
  - option: Matching-only operator-held never-git identity
    why_not: >
      Withdrawn. Chairman confirmed storage, product, repo, and research use
      (DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN). This PR still does not ingest
      rows; that is freeze scope, not a rights ban.
evidence:
  - "config/biocatalyst_sources.yml biopharmcatalyst_benchmark license_class benchmark_only, prohibited_uses includes proprietary_historical_row_import (soak-bound predecessor; unchanged)"
  - "research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md §2 — canonical identity frozen; runtime insertion deferred"
  - "DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK"
  - "PR #5909 Sol REQUEST CHANGES 2026-08-19"
  - "PR #5909 Sol FINAL ACCEPTANCE 2026-08-19"
  - "PR #5909 Sol CI RULING soak-safe freeze 2026-08-19"
affects:
  - "WS:BPC-JV-RECON"
  - "biocatalyst"
  - "config/biocatalyst_sources.yml"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

Partnership design makes BPC's continuous API unavailable. The authorized dump
is the only BPC evidence boundary. The benchmark source id already encodes
"do not import their rows" for the clean-room product. Licensed finite-snapshot
use is a different act and needs a different name so later successor-registry
tests can pin both. The live soak-bound YAML does not yet carry the JV row.
This record is Sol-accepted architecture (`decided_by: ceo-sol`).

## What would reopen this

Sol rejecting the distinct-id split, or an explicit Chairman instruction to
fold the JV snapshot into the benchmark identity.
