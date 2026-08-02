# Calcbench parity continuation handoff — 2026-08-02

## Stop point

Wave 2 is merged and live. Wave 3A is an **unmerged local checkpoint** and must not be presented as shipped or production-ready. An independent semantic audit found query/receipt correctness blockers after the 276-test integration pass, so this branch was deliberately held.

- Worktree: `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/calcbench-parity-wave3a-20260802`
- Branch: `codex/calcbench-parity-wave3a-20260802`
- Base HEAD: `33210f0565b83dfe828bbbb501abf8f7d978a13a`
- Canonical build docket: `research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md`
- This handoff is canonical for the pause/resume boundary.

## What is solid

The source/ledger lane has independently passed its full audit: durable `recorded_at` semantics, truthful byte accounting, bounded hostile-input handling, iterative/indexed ledger traversal, future-hidden revision invariance, strict SEC identities, and honest Company Facts dimensional limitations. Company Facts remains `point_in_time_eligible=false`; exact filing contexts belong in Wave 3B.

An attempted constructor-level metric-registry lane-inception patch passed its 24 focused tests but broke three legitimate future-governance query fixtures in the full suite. It was therefore reverted rather than left half-integrated. The permanent lane-inception contract remains required work below.

## What remains before Wave 3A can ship

The query/receipt layer still needs an independent re-audit of these fixes:

1. Entity authorization must come only from construction-time entities (or an explicit `QueryEntity`), never from future ledger contents.
2. Governance clocks are permanent lane-inception clocks; future definitions are append-only. Replacement/supersession is deferred.
3. Receipts need one full cutoff-visible governance bundle, exact mapping/formula contracts, ordered formula dependencies, recomputation, `source_entity_id`, and the selected immutable raw occurrence for direct values.
4. Dependency evidence must be a flat, deduplicated, bounded DAG—never recursive cell serialization. A standalone cell requires its bundle/DAG context.
5. Root identity is the root `duplicate_group_key`; agreeing duplicate roots must not be reported as unlinked.
6. Reject `system_ready_at < source_ready_at`.
7. Bound public constructor inputs with limit-plus-one admission before tuple/materialization or deep traversal.

Important proof boundary: an embedded selected raw occurrence proves the emitted value/entity/unit/concept/clock tuple. It does **not** prove selection optimality or absence of omitted facts; that still requires the immutable ledger. Wave 3B's `ffqs_*` snapshot is the intended standalone evidence layer.

## Resume sequence

1. Read `AGENTS.md`, this handoff, and the Wave 3A docket. Inspect `git status` before editing; preserve all unrelated work.
2. Verify the query checkpoint is coherent. The last independently audited pre-remediation hashes were:
   - `query.py`: `6d8de22f0742cfe1fcbe2c1edc3748f31a917c8529c8ab51b1e269676b4efb09`
   - `test_fundamental_forensics_query.py`: `83e3de7aefe15a23ebe373390150cf0b75dab229c861c0f6b2fdcfe219cd062e`
3. Finish the seven items above, add adversarial receipt-tamper and bounded-input tests, then commission a fresh independent semantic audit.
4. Run the full integration suite:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
     tests/test_fundamental_forensics_companyfacts.py \
     tests/test_fundamental_forensics_companyfacts_ledger.py \
     tests/test_fundamental_forensics_metric_registry.py \
     tests/test_fundamental_forensics_raw_ledger.py \
     tests/test_fundamental_forensics_periods.py \
     tests/test_fundamental_forensics_query.py \
     tests/test_fundamental_forensics_normalize.py \
     tests/test_fundamental_forensics_acquisition.py \
     tests/test_sec_document_spine.py
   ```

5. Only after the audit is clean: fetch `origin/main`, replay onto a fresh task branch/worktree, resolve the two upstream CI-file overlaps carefully, rerun validation, commit exact paths, open/merge the PR, and verify production under the repository ship contract.

## Wave 3B next lane (do not mix into Wave 3A)

Build filing-package acquisition and immutable query snapshots: bounded streamed filing indexes; safe no-network/no-DTD iXBRL/XML parsing; strict Company Facts attestation by CIK + accession + taxonomy + concept + canonical value + period + unit; and separate private `ffqs_*` Parquet snapshots with complete registry bundles, readback verification, and latest-pointer-last publication. Keep API/UI/Excel and scheduling out of the first Wave 3B PR.

No credentials or private tokens are required to resume this local checkpoint.

## Pause validation receipt

- The full suite before the isolated registry experiment passed 276 tests.
- The experiment's diagnostic run completed with 278 passed and 3 failed; all three failures were caused by over-constraining valid future-governance fixtures.
- The unfinished query rewrite was restored byte-for-byte to the two audited hashes above, and the isolated registry experiment was rolled back.
- Final frozen checkpoint: all 276 tests in the nine-file suite passed; the registry + query subset passed 66 tests; `py_compile` and `git diff --check` passed.
- Restored registry hashes: `metric_registry.py` `a79b738920e2f51e3aa838ad046fc18095495bc22932725c01ad8dd9d4cf0c2e`; registry test `3e703840ed8dad353a81d5ae9e1f11c7a912d5bdc9dbe3e3c6d09bf6ca70f2bf`.
