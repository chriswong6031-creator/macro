"""scripts/grade_operator_actions.py — DQ-2 operator-action grading runner.

Single writer for data/governance/operator_grading.json.

NEVER wired into daily.yml — ops-lane manual cadence only.

Usage::

    python -m scripts.grade_operator_actions                    # defaults
    python -m scripts.grade_operator_actions --data-root /path  # custom repo root
    python -m scripts.grade_operator_actions --ledger /path/to/action_ledger.jsonl
    python -m scripts.grade_operator_actions --out /path/to/output.json

Defaults:
  --data-root   .  (current directory = repo root)
  --ledger      <data-root>/data/operator/action_ledger.jsonl
  --out         <data-root>/data/governance/operator_grading.json

Output artifact carries a vintage stamp per engine/vintage_stamp.py convention.
Stamp fields use operator-grading-specific values (no price plane; action ledger
is the data plane here).  stamp_degraded=True is expected (no EDGAR dead-name file
relevant to this harness).

The artifact is expected to be in 'accruing' state until the operator action
ledger accumulates n>=25 graded actions per contrast.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("grade_operator_actions")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(
    data_root: Path,
    ledger_path: Path | None,
    out_path: Path,
) -> dict:
    """Grade operator actions and write the artifact.  Returns the artifact dict."""
    from engine.operator_grading import grade

    result = grade(data_root=data_root, ledger_path=ledger_path)

    # Build vintage stamp for the artifact
    # Stamp fields adapted to operator-grading context:
    #   price_plane_id      : "operator_action_ledger_v1"
    #   adjustment_mode     : "none"  (no price adjustment; action timestamps only)
    #   universe_as_of      : today's date
    #   frame               : "server_stamped_utc"
    #   survivorship_biased : False (ledger is append-only, no selection filter)
    #   coverage_frac       : fraction of actions with matched claims
    #   dead_name_coverage_pct : None (not applicable; stamp_degraded expected)
    #   era_law_cohort      : "all_time"
    n_total = result.get("n_actions_total", 0)
    n_matched = result.get("n_matched_actions", 0)
    coverage = round(n_matched / n_total, 4) if n_total > 0 else 0.0

    try:
        from engine.vintage_stamp import vintage_stamp
        stamp = vintage_stamp(
            price_plane_id="operator_action_ledger_v1",
            adjustment_mode="none",
            universe_as_of=datetime.now(timezone.utc).date().isoformat(),
            frame="server_stamped_utc",
            survivorship_biased=False,
            coverage_frac=coverage,
            dead_name_coverage_pct=None,   # not applicable; triggers stamp_degraded=True
            era_law_cohort="all_time",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("grade_operator_actions: vintage_stamp failed: %s", exc)
        stamp = {
            "price_plane_id": "operator_action_ledger_v1",
            "adjustment_mode": "none",
            "universe_as_of": datetime.now(timezone.utc).date().isoformat(),
            "frame": "server_stamped_utc",
            "survivorship_biased": False,
            "coverage_frac": coverage,
            "dead_name_coverage_pct": None,
            "era_law_cohort": "all_time",
            "stamp_degraded": True,
        }

    result["vintage_stamp"] = stamp
    result["generated_at"] = _now_iso()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    log.info("grade_operator_actions: wrote %s (state=%s)", out_path, result.get("state"))
    return result


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--data-root",
        default=".",
        help="Repo root for resolving claims/grades/trial_ledger (default: '.')",
    )
    ap.add_argument(
        "--ledger",
        default=None,
        help=(
            "Path to operator action_ledger.jsonl "
            "(default: <data-root>/data/operator/action_ledger.jsonl)"
        ),
    )
    ap.add_argument(
        "--out",
        default=None,
        help=(
            "Output path for the artifact JSON "
            "(default: <data-root>/data/governance/operator_grading.json)"
        ),
    )
    args = ap.parse_args()

    data_root = Path(args.data_root).resolve()
    ledger_path = Path(args.ledger).resolve() if args.ledger else None
    out_path = (
        Path(args.out).resolve()
        if args.out
        else data_root / "data" / "governance" / "operator_grading.json"
    )

    try:
        result = run(data_root=data_root, ledger_path=ledger_path, out_path=out_path)
        print(json.dumps({
            "state": result.get("state"),
            "n_actions_total": result.get("n_actions_total"),
            "n_matched_actions": result.get("n_matched_actions"),
            "n_unmatched_actions": result.get("n_unmatched_actions"),
            "out": str(out_path),
        }, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("grade_operator_actions: fatal: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
