"""Build the signal track-record log.

Thin runner mirroring scripts/build_signal_quality.py.  Calls
engine.track_record.update_track_record() with repo-relative defaults and
prints the summary dict.

Intended cadence: run after build_signal_quality.py (so site/signals/ and
data/signal_archive/mtf_signals_latest.json are fresh).

NEVER breaks a build: the body is wrapped in try/except; any error is logged
to stderr and the script exits 0 regardless.
"""
from __future__ import annotations

import sys
import logging
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

from engine.track_record import update_track_record  # noqa: E402


def main() -> None:
    try:
        summary = update_track_record()
        print(
            f"track_record: {summary['new_rows']} new rows, "
            f"{summary['matured_rows']} matured, "
            f"{summary['total_rows']} total, "
            f"{summary['skipped_pending']} pending skipped "
            f"-> {summary['out_path']}"
        )
    except Exception as exc:
        print(f"[build_track_record] ERROR (non-fatal): {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
