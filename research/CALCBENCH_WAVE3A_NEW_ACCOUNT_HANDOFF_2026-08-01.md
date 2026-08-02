# Calcbench parity — Wave 3A account handoff

## Resume point

- Worktree: `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/calcbench-parity-wave3a-resume-20260801`
- Branch: `codex/calcbench-parity-wave3a-resume-20260801`
- Base checkpoint: `50dd1999f79`
- This is an intentionally unmerged WIP checkpoint. Do not merge until the acceptance gate below is green.

## Current implementation

Wave 3A now contains a cutoff-projected `GovernanceBundle`, flat bounded `CellNode` receipt DAGs, strict cell/matrix deserialization, direct raw-occurrence evidence, formula recomputation, matrix query-hash verification, explicit proof-scope limits, entity/clock/duplicate-root fixes, and whole-receipt node/edge/byte ceilings.

Changed paths:

- `engine/fundamental_forensics/metric_registry.py`
- `engine/fundamental_forensics/query.py`
- `tests/test_fundamental_forensics_metric_registry.py`
- `tests/test_fundamental_forensics_query.py`

## Frozen validation

- `py_compile`: pass
- `git diff --check`: pass
- Registry + query focused run: **62 passed, 18 failed**
- The failures are migration/acceptance work, so Wave 3A is not shippable yet.

## First fixes

1. Preserve formula dependency order from `config/fundamental_forensics/formulas/core.yaml` (`gross_profit`, then `revenue`); update the stale assertion.
2. The future-governance test currently replaces the only revenue mapping and violates the append-only registry rule. Retain the old mapping and append the future mapping.
3. Update stale tests for the required `governance_bundle`, removed recursive `dependency_cells` / `registry_receipt` APIs, flat CSV pointers, and root-node period wire shape.
4. Add independent tamper tests for bundle identity, raw occurrence binding, formula recomputation, DAG reachability/cycles/dedup/order, entity authorization, duplicate roots, clock inversion, and limit-plus-one admission.

## Resume commands

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/calcbench-parity-wave3a-resume-20260801"
git status --short --branch
python3 -m py_compile engine/fundamental_forensics/metric_registry.py engine/fundamental_forensics/query.py
git diff --check
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_fundamental_forensics_metric_registry.py tests/test_fundamental_forensics_query.py -x
```

After focused acceptance is green, run the nine-suite command from `research/CALCBENCH_PARITY_CONTINUATION_HANDOFF_2026-08-02.md`, rebase onto fresh `origin/main`, rerun, then use the required PR → squash merge → production verification loop. Full Calcbench parity remains the active program; this checkpoint only pauses Wave 3A.
