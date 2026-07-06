"""scripts/build_options_entry_state.py — nightly builder for the options entry state table.

Writes data/options_entry/state.parquet (display-only per-ticker fusion table per RO-1).
See engine/options_entry_state.py for column spec and source details.

Runtime target: <60 seconds (light I/O; no network; reads committed parquet + JSON files).

Usage:
    .venv/bin/python -m scripts.build_options_entry_state
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Allow running as a standalone script from the repo root.
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.options_entry_state import build_state   # noqa: E402
from lib import config                               # noqa: E402

log = logging.getLogger(__name__)

OUTPUT_DIR = config.data_dir() / "options_entry"
OUTPUT_PATH = OUTPUT_DIR / "state.parquet"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    t0 = time.perf_counter()
    root = _REPO_ROOT

    df = build_state(root)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)

    elapsed = time.perf_counter() - t0
    n = len(df)
    eq_counts = df["evidence_quality"].value_counts().to_dict() if n else {}
    print(
        f"[build_options_entry_state] wrote {OUTPUT_PATH.relative_to(_REPO_ROOT)} "
        f"— {n} tickers, evidence_quality={eq_counts}, "
        f"elapsed={elapsed:.2f}s"
    )
    if elapsed > 60:
        log.warning(
            "build_options_entry_state exceeded 60s runtime budget (%.1fs) — "
            "investigate source I/O", elapsed
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
