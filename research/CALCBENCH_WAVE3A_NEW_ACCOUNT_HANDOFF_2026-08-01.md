# Calcbench parity — Wave 3A account handoff

## Resume point

- Worktree: `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/calcbench-wave3a-acceptance-20260801`
- Branch: `codex/calcbench-wave3a-acceptance-20260801`
- Status: the Wave 3A receipt-acceptance baseline is complete. This static memo
  is not deployment evidence; release/live state must be verified from Git and
  production health. Wave 3A is not a claim of full Calcbench parity.
- Canonical implementation docket:
  `research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md`.

## Current implementation

Wave 3A has a cutoff-projected `GovernanceBundle` and a flat, deduplicated,
bounded `CellNode` receipt DAG. A matrix carries one authoritative governance
bundle plus its bounded node set; a standalone cell needs that same bundle/DAG
context to be independently verified. The JSON sidecar is authoritative; CSV is
only a deterministic projection that points back to JSON receipt material.

Accepted receipt validation reconstructs all governed components that apply to a
cell: the cutoff-visible governance bundle, formula dependencies and arithmetic,
or the direct selected immutable raw occurrence. It also enforces the finite
shape of non-value branches rather than allowing a non-value result to smuggle
source or derivation evidence. Matrix validation proves the same contracts for
every flat node, with bounded node, edge, and decoded-wire budgets.

The implementation now additionally rejects source/policy/cutoff mismatches,
withdrawn direct facts, invalid source/revision combinations, invented evidence
for period-invalid cells, unbounded hostile mapping inputs, and constructor /
parser byte-accounting disagreements.

Changed implementation and test paths in this acceptance slice:

- `engine/fundamental_forensics/query.py`
- `tests/test_fundamental_forensics_metric_registry.py`
- `tests/test_fundamental_forensics_query.py`

## Proof boundary

The embedded selected raw occurrence proves consistency of the emitted value,
entity, unit, concept, period, source lineage, and visible clocks. It does not
prove that no eligible fact was omitted or that the chosen occurrence was globally
optimal. Those claims require an external immutable raw ledger (and, in Wave 3B,
a durable `ffqs_*` query snapshot). This is deliberately a selected-occurrence
consistency proof, not an absence or selection-optimality proof.

## Acceptance evidence

- Final focused registry + query suite: **93 passed**.
- Final nine-file integration suite: **303 passed**.
- Two independent semantic/DAG reviews reported no open P0/P1 correctness issue
  within the declared receipt proof scope.
- `py_compile` and `git diff --check` passed with the final acceptance set.

## Final verification and ship sequence

For a new release attempt, rerun these from the authoritative worktree:

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/calcbench-wave3a-acceptance-20260801"
python3 -m py_compile engine/fundamental_forensics/metric_registry.py engine/fundamental_forensics/query.py
git diff --check
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_fundamental_forensics_metric_registry.py \
  tests/test_fundamental_forensics_query.py
```

Then run the nine-suite command in the continuation handoff, fetch and rebase
onto fresh `origin/main`, rerun validation, and follow the repository PR → squash
merge → production-health verification contract. Update this section with final
test counts, merge SHA, and production evidence only after each is observed.

Full Calcbench parity remains a multi-wave program. This handoff covers only the
Wave 3A trustworthy bitemporal-receipt kernel.
