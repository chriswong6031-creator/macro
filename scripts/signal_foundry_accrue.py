"""scripts/signal_foundry_accrue.py — nightly forward-accrual runner (SF-R4).

Called from the daily.yml engine job after the causal commit step.  Calls
engine.signal_foundry.results.accrue_forward(repo_root, asof=today) and
prints a one-line summary.

Exits 0 even on internal errors (prints ::warning instead).  This is required
by the nightly-ledger law (SF-R4): failure of the accrual step must never
block the rest of the nightly pipeline.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Repo root: two levels up from this script
_REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    asof = date.today()
    try:
        from engine.signal_foundry.results import accrue_forward

        written = accrue_forward(_REPO_ROOT, asof=asof)

        total_written = sum(v for v in written.values() if v)
        n_specs = len(written)
        print(
            f"signal_foundry_accrue: asof={asof} specs_checked={n_specs} "
            f"rows_written={total_written}"
        )
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: print a GitHub Actions warning and exit 0
        print(
            f"::warning title=signal_foundry_accrue::accrual failed "
            f"(non-fatal): {exc}"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
