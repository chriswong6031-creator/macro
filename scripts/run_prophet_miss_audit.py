"""Thin runner for the Prophet US miss-audit engine (ops telemetry, ZERO authority).

All logic lives in :mod:`engine.prophet_miss_audit`; this file only parses flags and hands the
ledger gate through. See that module's docstring for the measurement, the two eligibility
bases, and the zero-authority contract.

NIGHTLY-ONLY LAW (nightly is the SOLE advancer of forward ledgers — CLAUDE.md; same pattern as
``scripts/grade_bottom_calls.py``'s ``--nightly``): the forward advance — writing
``data/prophet_miss_audit/latest.json`` and appending a summary row to
``data/prophet_miss_audit/forward_log.jsonl`` — happens ONLY under ``--nightly``. A default
invocation (intraday lane, re-render, local run) computes and prints and writes NOTHING, so an
off-nightly re-run can never advance the log. ``--out-dir DIR`` runs the full write into a
scratch dir, never the real store. The nightly append is additionally idempotent on
``price_through``, so a same-night re-run appends nothing either.

Both artifacts land on main through the daily job's existing "commit engine outputs"
(``git add data/``) step — the same persistence path every sibling forward ledger uses.

Run (nightly / DAG):   python -m scripts.run_prophet_miss_audit --nightly
Run (safe local test): python -m scripts.run_prophet_miss_audit --out-dir /tmp/pma
Run (dry, no writes):  python -m scripts.run_prophet_miss_audit
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import prophet_miss_audit as PMA  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="forward-advance: write the artifact + append the forward-log row "
                         "(the SOLE advancer; cron/DAG entry point)")
    ap.add_argument("--out-dir", default=None,
                    help="scratch dir for a safe local run (writes there, never the real store)")
    ap.add_argument("--no-cascade-basis", action="store_true",
                    help="skip the full-universe cascade pass (faster; "
                         "eligible_today_n_cascade reported null)")
    ap.add_argument("--no-gate", action="store_true",
                    help="skip the per-runner signal_gate pass (faster; gate_* fields absent)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    PMA.run(
        advance=bool(args.nightly),
        out_dir=Path(args.out_dir) if args.out_dir else None,
        quiet=args.quiet,
        with_gate=not args.no_gate,
        with_cascade_basis=not args.no_cascade_basis,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
