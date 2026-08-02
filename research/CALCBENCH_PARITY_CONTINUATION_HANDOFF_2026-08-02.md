# Calcbench parity continuation handoff — 2026-08-02

## Current stop point

The Wave 3A receipt-acceptance baseline is complete. This memo is not deployment
evidence; confirm release/live state from Git and production health. Do not
represent Wave 3A as full Calcbench parity.

- Worktree: `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/calcbench-wave3a-acceptance-20260801`
- Branch: `codex/calcbench-wave3a-acceptance-20260801`
- Canonical build docket:
  `research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md`
- This handoff is canonical for the Wave 3A acceptance/resume boundary.

## What Wave 3A now establishes

The source and ledger lanes retain bounded, append-only raw facts with distinct
source and system clocks. The query kernel adds one cutoff-visible
`GovernanceBundle` and a flat, deduplicated, bounded `CellNode` DAG. No receipt
uses recursive cell serialization. Formula cells recompute from dependency nodes;
direct value cells bind the selected immutable raw occurrence; non-value cells
are constrained to finite source-less, alias-lineage, or source-witness shapes.

The matrix JSON sidecar is the authoritative receipt object. CSV is a stable
projection, not a second receipt format. Matrix validation reconstructs the
governance/formula/direct-fact contract from the bundle and flat DAG, checks
hashes and all resource limits, and rejects clock, policy, entity, source,
withdrawal, revision, and period-rejection inconsistencies.

## Proof boundary

An accepted direct receipt proves selected-occurrence consistency: the emitted
value, entity, unit, concept, period, source lineage, mapping, and cutoff-visible
clocks agree. It does **not** prove the selected fact was globally optimal or
that all competing facts were absent; only an external immutable ledger can do
that. Wave 3B's durable `ffqs_*` snapshot is the intended standalone evidence
layer. Keep that boundary explicit in API and UI work.

## Acceptance status

- Final focused registry + query suite: **93 passed**.
- Final nine-file integration suite: **303 passed**.
- Two independent semantic/DAG reviews found no open P0/P1 correctness issue
  within the declared receipt proof scope.
- `py_compile` and `git diff --check` passed with the final acceptance set.

## Resume and final verification sequence

1. Read `AGENTS.md`, this handoff, and the Wave 3A docket. Inspect `git status`;
   preserve existing working changes in the acceptance worktree.
2. Preserve the clean independent-audit baseline. Retain strict bounded input
   admission and add a regression test for every future correctness fix.
3. Run syntax, diff, and focused acceptance checks:

   ```bash
   cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/calcbench-wave3a-acceptance-20260801"
   python3 -m py_compile engine/fundamental_forensics/metric_registry.py engine/fundamental_forensics/query.py
   git diff --check
   PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
     tests/test_fundamental_forensics_metric_registry.py \
     tests/test_fundamental_forensics_query.py
   ```

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

5. Only after those gates are green: fetch `origin/main`, rebase this clean task
   branch, rerun validation, commit only the session paths, open and squash-merge
   the PR, then verify the merge and production health under the repository ship
   contract. Record final counts, merge SHA, and live evidence here only after
   observing them.

## Wave 3B next lane (do not mix into Wave 3A)

Build filing-package acquisition and immutable query snapshots: bounded streamed
filing indexes; safe no-network/no-DTD iXBRL/XML parsing; strict Company Facts
attestation by CIK + accession + taxonomy + concept + canonical value + period +
unit; and separate private `ffqs_*` Parquet snapshots with complete governance
bundles, readback verification, and latest-pointer-last publication. Keep
API/UI/Excel and scheduling out of the first Wave 3B PR.

No credentials or private tokens are required to resume this local checkpoint.
