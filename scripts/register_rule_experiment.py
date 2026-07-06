"""scripts/register_rule_experiment.py — Registration CLI for rule experiments.

Single writer for data/rule_experiments/registry.jsonl.
This script is the ONLY path for appending to the registry (§3.3 house law).

Usage
-----
# Register a new experiment (interactive or scripted)
python scripts/register_rule_experiment.py \\
    --exp-id exit_grid_v1 \\
    --question "For the production fire cohort, what did each exit policy cost?" \\
    --spec-hashes abc123 def456 ... \\
    --verdict-criteria "descriptive-only" \\
    [--n-floor 300] \\
    [--derived-from-surface <prior_exp_id>]

# List all registered experiments
python scripts/register_rule_experiment.py --list

# Show pooled replay trial count
python scripts/register_rule_experiment.py --trial-count

# Update status of an existing experiment
python scripts/register_rule_experiment.py --update-status exit_grid_v1 executed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root as a script
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.rule_experiments import (  # noqa: E402
    VALID_STATUSES,
    list_experiments,
    pooled_replay_trial_count,
    reconcile_replay_accounting,
    register_experiment,
    update_experiment_status,
)


def cmd_register(args: argparse.Namespace) -> int:
    """Register a new experiment."""
    registry_path = Path(args.registry) if args.registry else None

    try:
        entry = register_experiment(
            exp_id=args.exp_id,
            question=args.question,
            spec_hashes=args.spec_hashes,
            declared_budget=len(args.spec_hashes),
            verdict_criteria=args.verdict_criteria,
            n_floor=args.n_floor,
            derived_from_surface=args.derived_from_surface,
            registry_path=registry_path,
        )
    except (ValueError, TypeError) as exc:
        print(f"[ERROR] Registration failed: {exc}", file=sys.stderr)
        return 1

    print(f"[REGISTERED] {entry['exp_id']}")
    print(f"  registered_at : {entry['registered_at']}")
    print(f"  declared_budget: {entry['declared_budget']}")
    print(f"  spec_hashes   : {entry['spec_hashes']}")
    print(f"  verdict_criteria: {entry['verdict_criteria']}")
    if entry.get("derived_from_surface"):
        print(f"  derived_from_surface: {entry['derived_from_surface']}")
    print()
    n = pooled_replay_trial_count(registry_path)
    print(f"  Cumulative pooled replay trial count: {n}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all experiments."""
    registry_path = Path(args.registry) if args.registry else None
    experiments = list_experiments(registry_path)
    if not experiments:
        print("No experiments registered.")
        return 0

    print(f"{'exp_id':<30} {'status':<12} {'budget':>8}  question[:60]")
    print("-" * 120)
    for e in sorted(experiments, key=lambda x: x.get("registered_at", "")):
        eid = e.get("exp_id", "?")
        status = e.get("status", "?")
        budget = e.get("declared_budget", "?")
        q = e.get("question", "")[:60]
        print(f"{eid:<30} {status:<12} {str(budget):>8}  {q}")

    n = pooled_replay_trial_count(registry_path)
    print()
    print(f"Cumulative pooled replay trial count: {n}")
    return 0


def cmd_trial_count(args: argparse.Namespace) -> int:
    """Print pooled replay trial count (both disclosure bases + drift check)."""
    registry_path = Path(args.registry) if args.registry else None
    n = pooled_replay_trial_count(registry_path)
    print(f"Cumulative pooled replay trial count (registry SUM basis): {n}")
    rec = reconcile_replay_accounting(registry_path)
    print(f"Trial-ledger max()-basis floor (DSR): {rec['ledger_max_floor']}")
    if not rec["consistent"]:
        print("[WARN] registry/ledger replay accounting DRIFT:", file=sys.stderr)
        for eid, pair in sorted(rec["mismatches"].items()):
            print(
                f"  {eid}: registry={pair['registry']} ledger={pair['ledger']}",
                file=sys.stderr,
            )
        for reason in rec["unattributed_ledger_rows"]:
            print(f"  unattributed ledger row: {reason!r}", file=sys.stderr)
        return 1
    return 0


def cmd_update_status(args: argparse.Namespace) -> int:
    """Update experiment status."""
    if args.new_status not in VALID_STATUSES:
        print(
            f"[ERROR] status {args.new_status!r} not in {sorted(VALID_STATUSES)}",
            file=sys.stderr,
        )
        return 1
    registry_path = Path(args.registry) if args.registry else None
    try:
        update = update_experiment_status(
            args.exp_id,
            args.new_status,
            registry_path=registry_path,
        )
    except KeyError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[UPDATED] {update['exp_id']} → {update['status']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rule experiment registry CLI — single writer for registry.jsonl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--registry",
        metavar="PATH",
        help="Override registry file path (default: data/rule_experiments/registry.jsonl)",
    )

    _REGISTRY_HELP = "Override registry file path (default: data/rule_experiments/registry.jsonl)"
    sub = parser.add_subparsers(dest="cmd")

    # --- register ---
    p_reg = sub.add_parser("register", help="Register a new experiment")
    p_reg.add_argument("--registry", metavar="PATH", help=_REGISTRY_HELP)
    p_reg.add_argument("--exp-id", required=True, help="Kebab-slug experiment ID")
    p_reg.add_argument("--question", required=True, help="One-sentence research question")
    p_reg.add_argument(
        "--spec-hashes",
        nargs="+",
        required=True,
        metavar="HASH",
        help="sha256 content hashes for every RuleSpec in the grid",
    )
    p_reg.add_argument(
        "--verdict-criteria",
        required=True,
        help='Frozen verdict criteria or literal "descriptive-only"',
    )
    p_reg.add_argument(
        "--n-floor",
        type=int,
        default=300,
        help="Minimum verdict-grade fires per cell (default: 300)",
    )
    p_reg.add_argument(
        "--derived-from-surface",
        default=None,
        metavar="EXP_ID",
        help="exp_id of a prior descriptive surface (RUL-P3 forking-paths honesty stamp)",
    )
    p_reg.set_defaults(func=cmd_register)

    # --- list ---
    p_list = sub.add_parser("list", help="List all registered experiments")
    p_list.add_argument("--registry", metavar="PATH", help=_REGISTRY_HELP)
    p_list.set_defaults(func=cmd_list)

    # --- trial-count ---
    p_tc = sub.add_parser("trial-count", help="Show cumulative pooled replay trial count")
    p_tc.add_argument("--registry", metavar="PATH", help=_REGISTRY_HELP)
    p_tc.set_defaults(func=cmd_trial_count)

    # --- update-status ---
    p_upd = sub.add_parser("update-status", help="Update experiment lifecycle status")
    p_upd.add_argument("--registry", metavar="PATH", help=_REGISTRY_HELP)
    p_upd.add_argument("exp_id", help="Experiment ID to update")
    p_upd.add_argument(
        "new_status",
        choices=sorted(VALID_STATUSES),
        help="New lifecycle status",
    )
    p_upd.set_defaults(func=cmd_update_status)

    args = parser.parse_args()

    if args.cmd is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
