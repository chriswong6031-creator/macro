"""scripts/register_disp_gate_1.py — Register the DISP-GATE-1 experiment.

Per §6.2 of CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md and
research/dispersion/L3_PREREG.md.

6 primary cells:
    regime arm {lean_in, neutral, lean_out}
    × basis {expanding-window (primary), trailing-252d (sensitivity)}

Declared budget: 6  →  post-B2 pooled sum = 31 (15 + 10 + 6).

SPY-21d contemporaneous drawdown covariate is a registered design obligation
(L3_PREREG design obligation 2) — reported as tercile-split adjustment WITHIN
cells, not as extra verdict cells.

Run:
    cd /path/to/repo && python scripts/register_disp_gate_1.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.rule_experiments import (  # noqa: E402
    pooled_replay_trial_count,
    register_experiment,
)
from engine.rule_replay import (  # noqa: E402
    ExitPolicy,
    RuleSpec,
    cohort_filter,
)
from scripts.run_rule_replay import _DISP_MERGE_COLS  # noqa: E402

# ---------------------------------------------------------------------------
# Frozen spec hashes (must match _build_disp_gate_1_specs in run_rule_replay.py)
# ---------------------------------------------------------------------------

def _build_specs() -> list[RuleSpec]:
    """Build the DISP-GATE-1 specs to compute their content hashes."""
    from scripts.run_rule_replay import _build_disp_gate_1_specs  # noqa: WPS433

    base_cohort = cohort_filter(
        ("eq", "verdict_type", "fire"),
        ("eq", "verdict_grade", True),
    )
    return _build_disp_gate_1_specs(base_cohort)


def main() -> int:
    specs = _build_specs()
    hashes = [s.content_hash() for s in specs]
    spec_ids = [s.spec_id for s in specs]

    print("DISP-GATE-1 grid:")
    for spec_id, h in zip(spec_ids, hashes):
        print(f"  {spec_id:45s}  hash={h[:16]}")
    print()

    # Check current pooled count before registration
    rp = _REPO_ROOT / "data" / "rule_experiments" / "registry.jsonl"
    pre_count = pooled_replay_trial_count(rp)
    print(f"Pre-registration pooled replay trial count: {pre_count}")

    question = (
        "DISP-GATE-1 (L3_PREREG.md, frozen 2026-07-05): "
        "For the production fire cohort, do fires opened when the broad-universe "
        "cross-sectional dispersion regime is lean_out (low dispersion / high "
        "pairwise correlation, macro-driven tape) show worse stop-5 and dead-money "
        "fractions at 21d than fires opened in lean_in (high dispersion, selection "
        "pays)? Grid: regime {lean_in, neutral, lean_out} x basis {expanding "
        "(primary, PIT-correct per L3_PREREG design obligation 1), trailing252 "
        "(sensitivity)}. SPY-21d contemporaneous drawdown covariate reported as "
        "tercile-split within cells (not extra verdict cells, per design obligation 2). "
        "Descriptive-only this batch; PASS thresholds frozen in L3_PREREG.md are "
        "read only at a later verdict batch."
    )

    # Base cohort: common predicates shared by all 6 cells.
    # The regime-state predicate is per-cell (handled by replay_spec);
    # disp_excluded=False is a base predicate shared by all cells.
    base_cohort_predicates = [
        ["eq", "verdict_type", "fire"],
        ["eq", "verdict_grade", True],
        ["eq", "disp_excluded", False],
    ]

    entry = register_experiment(
        exp_id="disp_gate_1",
        question=question,
        spec_hashes=hashes,
        declared_budget=6,
        verdict_criteria="descriptive-only",
        n_floor=25,  # L3_PREREG: min 25 episode clusters (not raw fires) per arm
        derived_from_surface=None,  # No prior surface seen (L3_PREREG pre-dates any run)
        needed_merge_columns=_DISP_MERGE_COLS,
        base_cohort_predicates=base_cohort_predicates,
        registry_path=rp,
    )

    post_count = pooled_replay_trial_count(rp)
    print(f"\n[REGISTERED] {entry['exp_id']}")
    print(f"  declared_budget : {entry['declared_budget']}")
    print(f"  verdict_criteria: {entry['verdict_criteria']}")
    print(f"  needed_merge_columns: {entry.get('needed_merge_columns', [])}")
    print()
    print(f"Post-registration pooled replay trial count: {post_count}")
    print(f"  (max()-basis note: TrialLedger.effective_n() uses max() semantics "
          f"and will report {max(15, 10, 6)} for this family, not the SUM. "
          "The honest cumulative SUM for FDR accounting is the registry sum above.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
